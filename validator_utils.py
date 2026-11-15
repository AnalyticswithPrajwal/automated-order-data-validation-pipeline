import boto3
from datetime import datetime
import configparser
from pathlib import Path


def credentials():
    config = configparser.ConfigParser()
    config_path = Path(__file__).resolve().parent / "config.ini"

    if not config.read(config_path):
        raise FileNotFoundError(config_path)

    return (
        config["aws"]["access_key"].strip(),
        config["aws"]["secret_key"].strip(),
        config["gmail_app_password"]["password"].strip()
    )


access_key, secret_key, gmail_app_key = credentials()

s3 = boto3.client(
    "s3",
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key
)


def load_product_master(bucket_name, master_key):
    products = {}

    response = s3.get_object(
        Bucket=bucket_name,
        Key=master_key
    )

    lines = response["Body"].read().decode("utf-8").splitlines()

    for line in lines[1:]:
        parts = line.strip().split(",")

        if len(parts) != 4:
            raise ValueError(f"Invalid product master row: {line}")

        product_id, product_name, price, category = parts

        try:
            products[product_id.strip()] = float(price)
        except ValueError:
            raise ValueError(f"Invalid product price: {price}")

    return products


def validate_line(fields, products, current_date):
    reasons = []

    if len(fields) != 6:
        return ["Incorrect number of fields"]

    order_id, order_date, product_id, quantity, total_sales_amount, city = [
        f.strip() for f in fields
    ]

    if any(not field for field in fields):
        reasons.append("Empty fields present")

    if product_id not in products:
        reasons.append("Invalid product ID")

    quantity_val = None
    amount_val = None

    try:
        quantity_val = int(quantity)

        if quantity_val <= 0:
            reasons.append("Quantity must be positive")

    except ValueError:
        reasons.append("Invalid quantity format")

    try:
        amount_val = float(total_sales_amount)

        if amount_val < 0:
            reasons.append("Negative sales amount")

    except ValueError:
        reasons.append("Invalid total_sales_amount format")

    if (
        product_id in products
        and quantity_val is not None
        and amount_val is not None
    ):
        expected_amount = products[product_id] * quantity_val

        if round(expected_amount, 2) != round(amount_val, 2):
            reasons.append("Incorrect total_sales_amount")

    try:
        order_date_val = datetime.strptime(
            order_date, "%d-%m-%Y"
        ).date()

        if order_date_val > current_date.date():
            reasons.append("Order date is in the future")

    except ValueError:
        reasons.append("Invalid order_date format")

    if city not in ["Mumbai", "Bangalore"]:
        reasons.append("Invalid city")

    return reasons


def read_s3_file(bucket_name, key):
    response = s3.get_object(
        Bucket=bucket_name,
        Key=key
    )

    content = response["Body"].read().decode("utf-8")

    return content.splitlines()


def write_s3_file(bucket_name, key, lines):
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body="\n".join(lines).encode("utf-8")
    )


def copy_s3_file(bucket_name, src_key, dest_key):
    s3.copy_object(
        Bucket=bucket_name,
        CopySource={
            "Bucket": bucket_name,
            "Key": src_key
        },
        Key=dest_key
    )


def delete_s3_file(bucket_name, key):
    s3.delete_object(
        Bucket=bucket_name,
        Key=key
    )
