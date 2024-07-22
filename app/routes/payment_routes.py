from flask import render_template, request, jsonify
from app import app
import stripe

stripe.api_key = app.config['STRIPE_SECRET_KEY']

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.get_json()
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': data['name'],
                },
                'unit_amount': int(data['price'] * 100),
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='http://localhost:5000/success',
        cancel_url='http://localhost:5000/cancel',
    )
    return jsonify(id=session.id)
