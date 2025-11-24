# Fix inheritance - SoftDeleteModel already inherits from TimeStampedModel
with open('apps/bots/models.py', 'r') as f:
    content = f.read()

# Replace multiple inheritance with just SoftDeleteModel
content = content.replace('(TimeStampedModel, SoftDeleteModel)', '(SoftDeleteModel)')

# For Order and TechnicalIndicator that don't need soft delete, use only TimeStampedModel
# They're currently just using TimeStampedModel, so they're fine

with open('apps/bots/models.py', 'w') as f:
    f.write(content)

print("Fixed model inheritance")
