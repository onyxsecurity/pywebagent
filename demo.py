import argparse
from pywebagent import act

def main(demo):
    raise Exception("Fill your credentials in demo.py") # !! Remove this line after filling your credentials !!

    if demo == "mixtiles":
        act(
            "https://mixtiles.com/",
            "Order these as Mixtiles",
            name="<your name>",
            email="<your email>",
            photos=[
                "demo/mixtiles/1.jpg",
                "demo/mixtiles/2.jpg",
                "demo/mixtiles/3.jpg"
            ],
            payment_info={
                "card_number": "<your card number>",
                "expiry_date": "<your expiry date>",
                "cvc": "<your cvc>"
            },
            address="<your address>"
        )
    elif demo == "amazon":
        act(
            "https://amazon.com/",
            "Buy a rabbit stuffed animal",
            email="<your email>",
            password="<your password>",
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", required=True, choices=["mixtiles", "amazon"])
    args = parser.parse_args()
    main(args.demo)

