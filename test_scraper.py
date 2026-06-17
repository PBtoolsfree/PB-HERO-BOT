import requests
import re

html = requests.get('https://www.desidime.com', headers={'User-Agent': 'Mozilla/5.0'}).text
pattern = re.compile(r'href="(/deals/[^"]+)".*?<span class="font-medium">\s*(.*?)\s*</span>', re.DOTALL)
matches = pattern.findall(html)
print(f"Found {len(matches)} deals")
for match in matches[:5]:
    print(f"Title: {match[1]}")
    print(f"Link: https://www.desidime.com{match[0].split('?')[0]}")
    print("---")
