import re

text = 'VW 109cm (43) Full HD Smart QLED Android TV\n⚡ ₹ 29,999 | ₹14,999\n👉 amzaff.to/ZLR2Fdx\n\nAlso check out example.com and v2.0'
URL_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d+)?(?:/[^\s<>"]+)?',
    re.IGNORECASE
)

print(URL_REGEX.findall(text))
