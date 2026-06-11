import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings
from generation_two.evolution.alpha_evolution_engine import AlphaEvolutionEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    tester.executor = ThreadPoolExecutor(max_workers=3)

    settings = SimulationSettings(
        region="USA",
        testPeriod="P5Y0M0D",
        neutralization="INDUSTRY",
        truncation=0.08
    )

    base_alphas = [
        "ts_mean(anl4_adjusted_netincome_ft, 5)",
        "anl4_adjusted_netincome_ft * anl4_capex_flag",
        "trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9, anl4_bvps_flag, -1)"
    ]
    
    alphas_to_test = []
    engine = AlphaEvolutionEngine(mutation_rate=1.0)
    
    for base_alpha in base_alphas:
        logging.info(f"Generating mutations for Base Alpha: {base_alpha}")

        # 1. Domain-Knowledge Mutations
        alphas_to_test.extend([
            f"group_rank({base_alpha}, subindustry)",
            f"trade_when(returns < ts_mean(returns, 5), {base_alpha}, -1)",
            f"ts_decay_exp_window({base_alpha}, 5, 2)",
            f"{base_alpha} - ts_mean(group_mean({base_alpha}, 5, market), 5)",
            f"ts_rank({base_alpha}, 20)",
            f"ts_zscore({base_alpha}, 20)",
            f"rank({base_alpha})"
        ])
        
        # specific domain knowledge requiring raw fields
        alphas_to_test.append(f"({base_alpha}) * volume / ts_mean(volume, 5)")

        # 2. Native Project Genetic Algorithm (AlphaEvolutionEngine)
        for _ in range(5):
            mutated = engine.mutate(base_alpha)
            if mutated not in alphas_to_test and mutated != base_alpha:
                alphas_to_test.append(mutated)

    # De-duplicate
    alphas_to_test = list(set(alphas_to_test))

    logging.info(f"Total Alphas to Auto-Simulate and Submit: {len(alphas_to_test)}")
    for a in alphas_to_test:
        logging.info(f" - {a}")
        
    futures = tester.simulate_batch(alphas_to_test, "USA", settings)
    
    logging.info("Waiting for all simulations to complete (max 10 minutes)...")
    results = tester.wait_for_results(futures, timeout=600)
    
    success_count = 0
    
    for res in results:
        if not res.success:
            logging.warning(f"❌ Failed Simulation: {res.template} -> {res.error_message}")
            continue
            
        logging.info(f"✅ Success: {res.template} -> Sharpe: {res.sharpe:.2f}, Fitness: {res.fitness:.2f}")
        
        if res.sharpe > 1.25 and res.fitness > 1.0:
            logging.info(f"🌟 Submitting evolved Alpha ID: {res.alpha_id}...")
            submit_url = f"https://api.worldquantbrain.com/alphas/{res.alpha_id}/submit"
            submit_req = sess.post(submit_url)
            
            if submit_req.status_code in [200, 201]:
                logging.info(f"🌟 Request sent successfully for 30-min PENDING test. (ID: {res.alpha_id})")
                success_count += 1
            else:
                logging.error(f"Failed to submit to PENDING: HTTP {submit_req.status_code}")

    logging.info(f"Evolution Pipeline Complete! Sent {success_count} evolved alphas into the Brain Matrix.")

if __name__ == "__main__":
    main()
