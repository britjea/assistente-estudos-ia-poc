"""Gera uma imagem sintética simples de um exercício escolar, só para testar
o POC sem depender de fotos reais. Rode com: python test_images/gerar_exemplo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 900, 500
img = Image.new("RGB", (LARGURA, ALTURA), color="white")
draw = ImageDraw.Draw(img)

try:
    fonte_titulo = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
    fonte_texto = ImageFont.truetype("DejaVuSans.ttf", 30)
except OSError:
    fonte_titulo = ImageFont.load_default()
    fonte_texto = ImageFont.load_default()

draw.text((40, 40), "Exercício de Matemática — 5º ano", font=fonte_titulo, fill="black")
draw.line((40, 95, LARGURA - 40, 95), fill="black", width=2)

draw.text((40, 160), "1) Maria tinha 7 maçãs.", font=fonte_texto, fill="black")
draw.text((40, 210), "Ela comprou mais 5 maçãs no mercado.", font=fonte_texto, fill="black")
draw.text((40, 280), "Quantas maçãs Maria tem agora?", font=fonte_texto, fill="black")

draw.rectangle((40, 380, 400, 440), outline="black", width=2)
draw.text((50, 390), "Resposta: ____", font=fonte_texto, fill="black")

destino = Path(__file__).parent / "exemplo_matematica.png"
img.save(destino)
print(f"Imagem gerada em: {destino}")
