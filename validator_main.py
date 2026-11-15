import csv
from datetime import datetime
import boto3
import email_utility

from sql_connector import get_cursor

from validator_utils import (
    load_product_master,
    validate_line,
    read_s3_file,
    write_s3_file,
    copy_s3_file,
    delete_s3_file,
    credentials
)


# Configuration
bucket_name = "python-project-with-s3"
product_master_key = "product_master.csv"

access_key, secret_key, gmail_app_key = credentials()

s3 = boto3.client(
    "s3",
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key
)


def get_prefixes():
    date_str = datetime.now().strftime("%Y%m%d")

    return (
        f"incoming_files/{date_str}/",
        f"success_files/{date_str}/",
        f"rejected_files/{date_str}/"
    )


def list_incoming_files(base_prefix):

    paginator = s3.get_paginator("list_objects_v2")

    files = []

    for page in paginator.paginate(
        Bucket=bucket_name,
        Prefix=base_prefix
    ):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                files.append(obj["Key"])

    return files


def process_file(file_key, products):

    lines = read_s3_file(bucket_name, file_key)

    if not lines:
        return False, "", [], []

    header = lines[0]

    data_lines = lines[1:]

    file_valid = True
    rejected_lines = []
    valid_lines = []

    for line in data_lines:

        fields = next(csv.reader([line]))

        reasons = validate_line(
            fields,
            products,
            datetime.now()
        )

        if reasons:

            file_valid = False

            rejected_lines.append(
                fields + [";".join(reasons)]
            )

        else:
            valid_lines.append(fields)

    return file_valid, header, rejected_lines, valid_lines


def main():

    base_prefix, success_prefix, rejected_prefix = get_prefixes()

    products = load_product_master(
        bucket_name,
        product_master_key
    )

    files = list_incoming_files(base_prefix)

    total = len(files)
    success = 0
    fail = 0

    cursor = None
    conn = None

    try:

        cursor, conn = get_cursor()

        insert_query = """
            INSERT INTO orders
            (
                order_id,
                order_date,
                product_id,
                quantity,
                total_sales_amount,
                city
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """

        for file_key in files:

            file_name = file_key.split("/")[-1]

            print(f"Processing: {file_name}")

            file_valid, header, rejected_lines, valid_lines = (
                process_file(file_key, products)
            )

            if file_valid:

                dest_key = success_prefix + file_name

                copy_s3_file(
                    bucket_name,
                    file_key,
                    dest_key
                )

                data = [
                    (
                        row[0],
                        datetime.strptime(row[1], "%d-%m-%Y").date(),
                        row[2],
                        int(row[3]),
                        float(row[4]),
                        row[5]
                    )
                    for row in valid_lines
                ]

                if data:
                    cursor.executemany(insert_query, data)

                conn.commit()

                # Delete source only after successful DB commit
                delete_s3_file(bucket_name, file_key)

                success += 1

                print(f"SUCCESS: {file_name}")

            else:

                dest_key = rejected_prefix + file_name

                copy_s3_file(
                    bucket_name,
                    file_key,
                    dest_key
                )

                error_key = rejected_prefix + "error_" + file_name

                error_content = [
                    header + ",rejection_reason"
                ]

                error_content.extend(
                    ",".join(
                        csv_row
                    )
                    for csv_row in rejected_lines
                )

                write_s3_file(
                    bucket_name,
                    error_key,
                    error_content
                )

                # Delete only after rejected file and error file
                # have been copied/written successfully
                delete_s3_file(bucket_name, file_key)

                fail += 1

                print(f"REJECTED: {file_name}")

    except Exception:

        if conn:
            conn.rollback()

        raise

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

    subject = (
        f"Validation Report "
        f"{datetime.now().strftime('%Y-%m-%d')}"
    )

    body = f"""
Total incoming files: {total}

Files passed validation: {success}

Files failed validation: {fail}
"""

    if total == 0:
        body = f"No incoming files found for {datetime.now():%Y-%m-%d}"

    email_utility.send_email_native(
        subject=subject,
        body=body,
        sender="YOUR EMAIL",
        password=gmail_app_key,
        recipient="RECEIVER EMAIL"
    )

    print("\n TASK COMPLETED")
    print(body)


if __name__ == "__main__":
    main()
