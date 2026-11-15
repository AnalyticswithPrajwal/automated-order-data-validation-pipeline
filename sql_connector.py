import pyodbc

def get_cursor():

    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        r"SERVER= YOUR SERVER NAME;"
        "DATABASE=python_project;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    cursor = conn.cursor()

    return cursor, conn
