"""Build EReseta's scalable eRx identity as Windows multi-resolution icons."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCALE = 4
image = Image.new('RGBA', (256*SCALE,256*SCALE), (0,0,0,0))
d = ImageDraw.Draw(image)
def box(bounds, radius, fill):
    d.rounded_rectangle(tuple(int(v*SCALE) for v in bounds), radius=radius*SCALE, fill=fill)
def text(x,y,label,size,color):
    font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',size*SCALE)
    d.text((x*SCALE,y*SCALE),label,font=font,fill=color,stroke_width=0,anchor='lt')
# A teal edge makes the navy tile recognizable on light and dark desktops.
box((5,5,251,251),54,'#21C7B7')
box((12,12,244,244),47,'#123954')
# A folded upper corner evokes an electronic prescription, without tiny details.
d.polygon([(188*SCALE,12*SCALE),(244*SCALE,68*SCALE),(203*SCALE,68*SCALE),(188*SCALE,53*SCALE)],fill='#21C7B7')
# Oversized custom composition survives small Windows icon sizes.
text(29,65,'e',108,'#FFFFFF')
text(96,50,'R',130,'#FFFFFF')
text(160,139,'x',73,'#C4F46D')
# Signature stroke / electronic underline is part of the identity.
box((35,205,144,218),6,'#21C7B7')
assets=ROOT/'assets';assets.mkdir(exist_ok=True)
preview=image.resize((256,256),Image.Resampling.LANCZOS)
preview.save(assets/'ereseta-icon.png')
image.save(assets/'ereseta.ico',sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])
print('Built EReseta eRx icon in assets.')
