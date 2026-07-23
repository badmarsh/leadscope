import email.utils
import re

def classify_email(email_str: str) -> str:
    """
    Zero-dependency Python stdlib classifier for classifying contact emails as 'personal', 'role', or 'invalid'.
    Handles non-ASCII display names (e.g., "Ján Kováč <jan@firma.sk>") via email.utils.parseaddr.
    """
    if not email_str:
        return 'invalid'
        
    _, addr = email.utils.parseaddr(email_str)
    if not addr or '@' not in addr:
        return 'invalid'
        
    local, domain = addr.rsplit('@', 1)
    
    # Check basic valid characters
    if not re.match(r'^[a-zA-Z0-9_.+-]+$', local):
        return 'invalid'
    if not re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', domain):
        return 'invalid'

    # Role-based prefixes commonly found
    role_prefixes = {
        'info', 'contact', 'admin', 'sales', 'support', 'hello', 
        'marketing', 'office', 'press', 'media', 'billing', 'jobs', 
        'careers', 'hr', 'webmaster', 'help', 'team', 'enquiries',
        'kontakt', 'obchod', 'info', 'sekretariat', 'kancelaria'
    }
    
    if local.lower() in role_prefixes:
        return 'role'
        
    return 'personal'
