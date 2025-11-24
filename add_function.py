# Append get_client_ip function to core/utils.py
with open('core/utils.py', 'a') as f:
    f.write('\n\n')
    f.write('def get_client_ip(request):\n')
    f.write('    """Get client IP address from request."""\n')
    f.write('    x_forwarded_for = request.META.get(\'HTTP_X_FORWARDED_FOR\')\n')
    f.write('    if x_forwarded_for:\n')
    f.write('        ip = x_forwarded_for.split(\',\')[0].strip()\n')
    f.write('    else:\n')
    f.write('        ip = request.META.get(\'REMOTE_ADDR\')\n')
    f.write('    return ip\n')

print('Added get_client_ip function to core/utils.py')
