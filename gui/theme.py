"""
Cyberpunk Theme Configuration
"""

# Cyberpunk color palette
COLORS = {
    'bg_primary': '#0a0e27',      # Dark blue-black
    'bg_secondary': '#0f1629',     # Slightly lighter dark
    'bg_panel': '#1a1f3a',        # Panel background
    'accent_cyan': '#00ffff',      # Bright cyan
    'accent_pink': '#ff00ff',      # Bright pink
    'accent_green': '#00ff41',     # Matrix green
    'accent_yellow': '#ffff00',    # Yellow
    'text_primary': '#e0e0e0',     # Light gray
    'text_secondary': '#888888',   # Medium gray
    'text_dim': '#555555',        # Dim gray
    'border': '#00ffff',           # Cyan border
    'success': '#00ff41',          # Green
    'warning': '#ffff00',          # Yellow
    'error': '#ff0040',            # Red
    'glow': '#00ffff',             # Glow effect
}

FONTS = {
    'default': ('Consolas', 10),
    'heading': ('Consolas', 14, 'bold'),
    'title': ('Consolas', 18, 'bold'),
    'mono': ('Courier New', 9),
    'small': ('Consolas', 8),
}

STYLES = {
    'button': {
        'bg': COLORS['bg_panel'],
        'fg': COLORS['accent_cyan'],
        'activebackground': COLORS['bg_secondary'],
        'activeforeground': COLORS['accent_cyan'],
        'relief': 'flat',
        'borderwidth': 1,
        'highlightthickness': 1,
        'highlightbackground': COLORS['accent_cyan'],
        'font': FONTS['default'],
        'cursor': 'hand2',
    },
    'entry': {
        'bg': COLORS['bg_secondary'],
        'fg': COLORS['text_primary'],
        'insertbackground': COLORS['accent_cyan'],
        'relief': 'flat',
        'borderwidth': 1,
        'highlightthickness': 1,
        'highlightbackground': COLORS['accent_cyan'],
        'font': FONTS['mono'],
    },
    'label': {
        'bg': COLORS['bg_primary'],
        'fg': COLORS['text_primary'],
        'font': FONTS['default'],
    },
    'frame': {
        'bg': COLORS['bg_panel'],
        'relief': 'flat',
        'borderwidth': 1,
    },
}
