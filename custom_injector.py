import json
import logging
import time
import os
from concurrent.futures import Future, ThreadPoolExecutor

# Make sure we run from the correct directory so imports work
from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings, SimulationResult


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# The user's exact 9 templates
ALPHAS_TO_TEST = [
    "anl4_adjusted_netincome_ft * anl4_capex_flag",
    "ts_mean(anl4_bvps_flag, 5)",
    "trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9, anl4_bvps_flag, -1)",
    "group_neutralize(anl4_bvps_flag, industry)",
    "ts_mean(anl4_adjusted_netincome_ft, 5)",
    "group_rank(anl4_cff_number, subindustry)",
    "group_rank(anl4_cfo_number, subindustry)",
    "group_zscore(anl4_bvps_flag, market)",
    "group_rank(anl4_cfo_number, subindustry)"
]

def main():
    cm = CredentialManager(base_path="generation_two")
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        logging.error("Failed to authenticate.")
        return
        
    sess = cm.get_session()
    logging.info("Successfully logged in to WQ Brain!")

    region_configs = {}
    region_configs["USA"] = type('RegionConfig', (), {
        'region': "USA",
        'universe': "TOP3000",
        'delay': 1
    })()
    tester = SimulatorTester(session=sess, region_configs=region_configs)
    # Customize executor to respect concurrency limit
    tester.executor = ThreadPoolExecutor(max_workers=3)
    
    settings = SimulationSettings(
        region="USA", 
        testPeriod="P5Y0M0D", 
        neutralization="INDUSTRY", 
        truncation=0.08
    )

    logging.info(f"Submitting {len(ALPHAS_TO_TEST)} specific alpha formulas for simulation...")
    
    futures = tester.simulate_batch(ALPHAS_TO_TEST, "USA", settings)
    
    logging.info("Waiting for all simulations to complete (max 10 minutes)...")
    results = tester.wait_for_results(futures, timeout=600)
    
    with open("results_summary.csv", "w", encoding="utf-8") as f:
        f.write("Formula,Sharpe,Fitness,Turnover,Success,Submitted\n")
        
        for res in results:
            if not res.success:
                logging.warning(f"❌ Failed: {res.template} -> {res.error_message}")
                f.write(f'"{res.template}",0,0,0,False,False\n')
                continue
                
            logging.info(f"✅ Success: {res.template} -> Sharpe: {res.sharpe:.2f}, Fitness: {res.fitness:.2f}")
            
            submitted = False
            if res.sharpe > 1.25 and res.fitness > 1.0:
                logging.info(f"🌟 High score detected! Automatically submitting Alpha ID: {res.alpha_id}...")
                submit_url = f"https://api.worldquantbrain.com/alphas/{res.alpha_id}/submit"
                submit_req = sess.post(submit_url)
                
                if submit_req.status_code in [200, 201]:
                    logging.info("🌟 Submission Confirmed! Successfully recorded to WorldQuant portfolio.")
                    submitted = True
                else:
                    logging.error(f"Failed to submit: HTTP {submit_req.status_code}")
                
            f.write(f'"{res.template}",{res.sharpe},{res.fitness},{res.turnover},True,{submitted}\n')

    logging.info("All finished! Check results_summary.csv for full report.")

if __name__ == "__main__":
    main()
