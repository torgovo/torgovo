with open('config/settings/base.py', 'r') as f:
    content = f.read()

content = content.replace("AUTH_USER_MODEL = 'authentication.User'", "AUTH_USER_MODEL = 'authentication.CustomUser'")

with open('config/settings/base.py', 'w') as f:
    f.write(content)

print("Fixed AUTH_USER_MODEL to authentication.CustomUser")
