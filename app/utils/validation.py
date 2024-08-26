from wtforms import ValidationError

def validate_positive(form, field):
    if field.data <= 0:
        raise ValidationError("Field must be greater than zero.")

def validate_non_empty(form, field):
    if not field.data.strip():
        raise ValidationError("Field cannot be empty.")
