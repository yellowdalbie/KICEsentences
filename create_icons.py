import os
import subprocess
from pathlib import Path
from PIL import Image

def create_mac_icns(source_png: Path, output_icns: Path):
    iconset_dir = Path("icon.iconset")
    if iconset_dir.exists():
        import shutil
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)
    
    img = Image.open(source_png).convert("RGBA")
    
    # Mac icon naming requirements
    # size, suffix
    config = [
        (16, ""), (16, "@2x"),
        (32, ""), (32, "@2x"),
        (128, ""), (128, "@2x"),
        (256, ""), (256, "@2x"),
        (512, ""), (512, "@2x"),
    ]
    
    for size, suffix in config:
        pixel_size = size * 2 if suffix == "@2x" else size
        resized = img.resize((pixel_size, pixel_size), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / f"icon_{size}x{size}{suffix}.png")
            
    # Run iconutil
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns)], check=True)
        print(f"Created {output_icns}")
    except subprocess.CalledProcessError as e:
        print(f"iconutil failed: {e}")
        # Let's see what's in the folder
        print("Files in iconset:")
        for f in iconset_dir.glob("*.png"):
            print(f"  {f.name}")
        raise
    
    # Cleanup
    import shutil
    shutil.rmtree(iconset_dir)

def create_windows_ico(source_png: Path, output_ico: Path):
    img = Image.open(source_png)
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_ico, format='ICO', sizes=icon_sizes)

if __name__ == "__main__":
    src_png = Path("icon_source.png")
    
    # Create icons
    print("Creating icon.icns for Mac...")
    create_mac_icns(src_png, Path("icon.icns"))
    
    print("Creating icon.ico for Windows...")
    create_windows_ico(src_png, Path("icon.ico"))
    
    print("Icons created successfully!")
