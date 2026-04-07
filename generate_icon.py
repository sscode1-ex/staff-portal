"""
Run this once to generate icon.png in the static folder.
pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
import os

size = 192
img = Image.new('RGB', (size, size), color='#0a0a0f')
draw = ImageDraw.Draw(img)

# Draw a simple SP logo
draw.rectangle([20, 20, 172, 172], outline='#ff6b35', width=4)
draw.text((size//2, size//2), "SP", fill='#ff6b35', anchor='mm')

os.makedirs('static', exist_ok=True)
img.save('static/icon.png')
img.save('static/badge.png')
print("Icons generated.")
