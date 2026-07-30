import pytest
import email_validator

def test_classify_email_personal():
    assert email_validator.classify_email("john.doe@example.com") == "personal"
    assert email_validator.classify_email("Ján Kováč <jan@firma.sk>") == "personal"

def test_classify_email_role():
    assert email_validator.classify_email("info@company.com") == "role"
    assert email_validator.classify_email("sales@domain.org") == "role"
    assert email_validator.classify_email("kancelaria@firm.sk") == "role"

def test_classify_email_invalid():
    assert email_validator.classify_email("") == "invalid"
    assert email_validator.classify_email(None) == "invalid"
    assert email_validator.classify_email("not-an-email") == "invalid"
    assert email_validator.classify_email("user@invalid_domain!#.com") == "invalid"
