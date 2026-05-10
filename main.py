import asyncio
import sys
import os

async def main():
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    # pygame.locals is a pure-Python re-export that is absent in some pygbag
    # WASM builds. All the constants live on the pygame module itself.
    # Only copy constants (ALL_CAPS or K_ key codes) — never classes or
    # functions, which would shadow names like koon.input.Joystick.
    import pygame, types
    if 'pygame.locals' not in sys.modules:
        _m = types.ModuleType('pygame.locals')
        _m.__dict__.update({k: v for k, v in vars(pygame).items()
                            if k.isupper() or k.startswith('K_')})
        sys.modules['pygame.locals'] = _m
        pygame.locals = _m

    try:
        from monorail.monorail import async_main
        await async_main()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ERROR: {e}", flush=True)
        print(tb, flush=True)
        try:
            import platform as _plat
            box = _plat.window.document.getElementById("infobox")
            box.style.cssText = (
                "display:block!important;position:fixed;top:0;left:0;"
                "right:0;bottom:0;background:#300;color:#fff;"
                "font:11px monospace;padding:8px;z-index:99999;"
                "white-space:pre;overflow:auto;"
            )
            box.innerText = "PYTHON ERROR\n\n" + tb
        except Exception:
            pass

asyncio.run(main())
