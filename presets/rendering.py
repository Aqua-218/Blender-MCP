RENDER_PRESETS = {
    "preview": {
        "engine": "BLENDER_EEVEE",
        "resolution_x": 768,
        "resolution_y": 768,
        "samples": 24,
        "transparent_background": True,
    },
    "standard": {
        "engine": "BLENDER_EEVEE",
        "resolution_x": 1280,
        "resolution_y": 1280,
        "samples": 64,
        "transparent_background": True,
    },
    "final": {
        "engine": "CYCLES",
        "resolution_x": 1920,
        "resolution_y": 1920,
        "samples": 128,
        "transparent_background": True,
    },
    "thumbnail": {
        "engine": "BLENDER_EEVEE",
        "resolution_x": 320,
        "resolution_y": 320,
        "samples": 12,
        "transparent_background": True,
    },
}
