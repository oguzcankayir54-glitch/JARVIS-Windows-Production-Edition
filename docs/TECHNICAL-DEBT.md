# Teknik borç

## Panel HTML yapısı

`docs/mockups/jarvis-panel.html` yaklaşık 1.900 satırlık tek dosyadır. HTML,
CSS ve istemci JavaScript'i ileride davranış korunarak ayrı dosyalara
bölünebilir. Bu bakım işinde dosya bilerek bölünmedi: panel tasarımının ve
tek-dosya dağıtım yolunun değişmemesi daha önceliklidir. Bölme yapılacağı
zaman 1920×1080, 1366×768 ve 390×844 Playwright kutu ölçümleri önce/sonra
karşılaştırılmalı ve yerleşim farkı sıfır olmalıdır.
