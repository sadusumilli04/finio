from finio.services.demo_data import seed_demo_data

APPLE_CSV = (
    b"Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By\n"
    b'01/05/2025,01/06/2025,"WHOLE FOODS","Whole Foods","Grocery","Purchase","42.10","Test Person"\n'
)
VENMO_CSV = (
    b"Account Statement - (@test-user) ,,,,,,,,\n"
    b"Account Activity,,,,,,,,\n"
    b",ID,Datetime,Type,Status,Note,From,To,Amount (total)\n"
    b",7000000000000000001,2025-01-05T09:00:00,Payment,Complete,pizza,Test User,Person One,- $12.00\n"
)


def write_testdata(tmp_path):
    (tmp_path / "apple_card_2025.csv").write_bytes(APPLE_CSV)
    (tmp_path / "venmo_2025.csv").write_bytes(VENMO_CSV)
    return tmp_path


def test_seeds_two_accounts_with_transactions(conn, tmp_path):
    seed_demo_data(conn, write_testdata(tmp_path))
    accounts = conn.execute("SELECT name, source FROM accounts ORDER BY id").fetchall()
    assert [(a["name"], a["source"]) for a in accounts] == [
        ("Apple Card (sample)", "apple_card_csv"),
        ("Venmo (sample)", "venmo_csv"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2


def test_does_nothing_if_an_account_already_exists(conn, make_account, tmp_path):
    make_account()
    seed_demo_data(conn, write_testdata(tmp_path))
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_is_a_no_op_when_the_files_are_missing(conn, tmp_path):
    seed_demo_data(conn, tmp_path)  # empty directory, no csv files
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_calling_it_twice_does_not_duplicate(conn, tmp_path):
    write_testdata(tmp_path)
    seed_demo_data(conn, tmp_path)
    seed_demo_data(conn, tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 2
