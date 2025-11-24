# Script to comment out allauth in INSTALLED_APPS
import re

with open('config/settings/base.py', 'r') as f:
    content = f.read()

# Comment out allauth entries in THIRD_PARTY_APPS
content = content.replace("    'allauth',", "    # 'allauth',  # Temporarily disabled")
content = content.replace("    'allauth.account',", "    # 'allauth.account',")
content = content.replace("    'allauth.socialaccount',", "    # 'allauth.socialaccount',")
content = content.replace("    'allauth.socialaccount.providers.google',", "    # 'allauth.socialaccount.providers.google',")

# Comment out allauth middleware
content = content.replace("    'allauth.account.middleware.AccountMiddleware',", "    # 'allauth.account.middleware.AccountMiddleware',")

with open('config/settings/base.py', 'w') as f:
    f.write(content)

print("Commented out allauth from settings")
