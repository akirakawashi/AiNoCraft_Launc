from PIL import Image
img = Image.open(r'ui\img\logo.png').convert('RGBA')
img.save(r'ui\img\logo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
print('ICO created OK')
