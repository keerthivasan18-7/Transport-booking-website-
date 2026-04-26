from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import os
import sqlite3
from datetime import datetime, timedelta
import io
import re
import openrouteservice
from functools import wraps

app = Flask(__name__)

def get_env(name, default=None):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() if isinstance(value, str) else value

# Security-sensitive config from environment variables.
FLASK_SECRET_KEY = get_env("FLASK_SECRET_KEY", "dev-secret-key-change-me")
ORS_API_KEY = get_env("ORS_API_KEY", "")
ADMIN_USER = get_env("ADMIN_USER", "admin")
ADMIN_PASS = get_env("ADMIN_PASS", "password123")

app.secret_key = FLASK_SECRET_KEY
ors_client = openrouteservice.Client(key=ORS_API_KEY) if ORS_API_KEY else None

# Storage paths
DATABASE_FILE = "transport_booking.sqlite"
LEGACY_BOOKINGS_FILE = "customer_data.xlsx"
LEGACY_INVENTORY_FILE = "truck_inventory.xlsx"
LEGACY_COST_FILE = "cost_config.xlsx"

BOOKINGS_TABLE = "bookings"
INVENTORY_TABLE = "inventory"
COST_CONFIG_TABLE = "cost_config"

# Default inventory if missing
DEFAULT_INVENTORY = {
    "Tata Ace": 5,
    "Tata 407": 5,
    "Eicher 14ft": 5,
    "Eicher 17ft": 5,
    "BharatBenz 3123": 5
}

PROPERTY_TRUCK_MAPPING = {
    "Studio": "Tata Ace",
    "1 Room": "Tata 407",
    "2 Rooms": "Eicher 14ft",
    "3 Rooms": "Eicher 17ft",
    "4 Rooms": "BharatBenz 3123",
    "5 Rooms": "BharatBenz 3123",
}

CITY_OPTIONS = [
    "Toronto",
    "Vancouver",
    "Montreal",
    "Calgary",
    "Ottawa",
    "Edmonton",
    "Winnipeg",
    "Quebec City",
    "Hamilton",
    "Kitchener",
    "London",
    "Mississauga",
    "Brampton",
    "Surrey",
    "Halifax",
    "Saskatoon",
    "Regina",
    "Windsor",
    "Burnaby",
    "St. John's",
]

TRUCK_CAPACITY_ORDER = [
    "Tata Ace",
    "Tata 407",
    "Eicher 14ft",
    "Eicher 17ft",
    "BharatBenz 3123",
]

DEFAULT_COST_CONFIG = {
    "Labour_per_km": 0.2,
    "Profit_per_km": 2,
    "Fuel_price_per_litre": 1.5,
    "Tata Ace_mileage": 12,
    "Tata 407_mileage": 8,
    "Eicher 14ft_mileage": 6,
    "Eicher 17ft_mileage": 5,
    "BharatBenz 3123_mileage": 4,
    "Studio_packing": 20,
    "1 Room_packing": 40,
    "2 Rooms_packing": 60,
    "3 Rooms_packing": 80,
    "4 Rooms_packing": 100,
    "5 Rooms_packing": 120,
}

DEFAULT_INVENTORY_DF = pd.DataFrame(list(DEFAULT_INVENTORY.items()), columns=["Truck Type", "Available"])

def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

def table_exists(table_name):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None

def table_row_count(table_name):
    if not table_exists(table_name):
        return 0

    with get_db_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row else 0

def read_table_df(table_name):
    if not table_exists(table_name):
        return pd.DataFrame()

    with get_db_connection() as conn:
        try:
            return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        except Exception:
            return pd.DataFrame()

def write_table_df(table_name, df):
    with get_db_connection() as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)

def save_cost_config(config):
    config_df = pd.DataFrame(
        [(str(key), value) for key, value in config.items()],
        columns=["config_key", "config_value"],
    )
    write_table_df(COST_CONFIG_TABLE, config_df)

def load_cost_config_from_legacy_workbook():
    if not os.path.exists(LEGACY_COST_FILE):
        return None

    try:
        kv_df = pd.read_excel(LEGACY_COST_FILE, index_col=0)
        if "Value" in kv_df.columns:
            return {str(key): value for key, value in kv_df["Value"].to_dict().items()}
    except Exception:
        pass

    try:
        raw_df = pd.read_excel(LEGACY_COST_FILE, header=None)
        header_idx = None
        for idx, row in raw_df.iterrows():
            if str(row.iloc[0]).strip() == "Property Size":
                header_idx = idx
                break

        if header_idx is None:
            return None

        table = pd.read_excel(LEGACY_COST_FILE, header=header_idx)
        table.columns = [str(c).strip() for c in table.columns]
        table = table.dropna(subset=["Property Size", "Truck Type"])

        config = dict(DEFAULT_COST_CONFIG)

        first_row = table.iloc[0]
        if "Labour Rate ($/km)" in table.columns and pd.notna(first_row.get("Labour Rate ($/km)")):
            config["Labour_per_km"] = float(first_row["Labour Rate ($/km)"])
        if "Profit Rate ($/km)" in table.columns and pd.notna(first_row.get("Profit Rate ($/km)")):
            config["Profit_per_km"] = float(first_row["Profit Rate ($/km)"])
        if "Fuel Price ($/l)" in table.columns and pd.notna(first_row.get("Fuel Price ($/l)")):
            config["Fuel_price_per_litre"] = float(first_row["Fuel Price ($/l)"])

        for _, row in table.iterrows():
            property_size = str(row["Property Size"]).strip()
            truck_type = str(row["Truck Type"]).strip()
            if "Packing Cost" in table.columns and pd.notna(row.get("Packing Cost")):
                config[f"{property_size}_packing"] = float(row["Packing Cost"])
            if "Mileage (km/l)" in table.columns and pd.notna(row.get("Mileage (km/l)")):
                config[f"{truck_type}_mileage"] = float(row["Mileage (km/l)"])

        return config
    except Exception:
        return None

def ensure_sqlite_storage():
    if not table_exists(INVENTORY_TABLE) or table_row_count(INVENTORY_TABLE) == 0:
        if os.path.exists(LEGACY_INVENTORY_FILE):
            try:
                legacy_inventory = pd.read_excel(LEGACY_INVENTORY_FILE)
                if not legacy_inventory.empty:
                    write_table_df(INVENTORY_TABLE, legacy_inventory)
                else:
                    write_table_df(INVENTORY_TABLE, DEFAULT_INVENTORY_DF)
            except Exception:
                write_table_df(INVENTORY_TABLE, DEFAULT_INVENTORY_DF)
        else:
            write_table_df(INVENTORY_TABLE, DEFAULT_INVENTORY_DF)

    if not table_exists(COST_CONFIG_TABLE) or table_row_count(COST_CONFIG_TABLE) == 0:
        legacy_config = load_cost_config_from_legacy_workbook()
        if legacy_config is None:
            legacy_config = dict(DEFAULT_COST_CONFIG)
        save_cost_config(legacy_config)

    if not table_exists(BOOKINGS_TABLE) and os.path.exists(LEGACY_BOOKINGS_FILE):
        try:
            legacy_bookings = pd.read_excel(LEGACY_BOOKINGS_FILE)
            if not legacy_bookings.empty:
                save_bookings(legacy_bookings)
        except Exception:
            pass

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            # Redirect to the 'login' endpoint
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def load_cost_config():
    if table_exists(COST_CONFIG_TABLE):
        config_df = read_table_df(COST_CONFIG_TABLE)
        if not config_df.empty and {"config_key", "config_value"}.issubset(config_df.columns):
            return {
                str(row["config_key"]): row["config_value"]
                for _, row in config_df.iterrows()
            }

    legacy_config = load_cost_config_from_legacy_workbook()
    if legacy_config is not None:
        save_cost_config(legacy_config)
        return legacy_config

    save_cost_config(dict(DEFAULT_COST_CONFIG))
    return dict(DEFAULT_COST_CONFIG)

def calculate_distance_duration(pickup, drop):
    try:
        if ors_client is None:
            raise RuntimeError("ORS_API_KEY is not configured")

        geocode = lambda place: ors_client.pelias_search(text=place)['features'][0]['geometry']['coordinates']
        coords = (geocode(pickup), geocode(drop))
        route = ors_client.directions(coords, profile='driving-car', format='geojson')
        summary = route['features'][0]['properties']['summary']
        return round(summary['distance'] / 1000, 2), round(summary['duration'] / 60, 2)
    except Exception as e:
        print("Routing error:", e)
        # Fallback for API/Key errors to keep the application running locally
        return 100, 120 # Default distance/duration if API fails

def load_bookings():
    df = read_table_df(BOOKINGS_TABLE)
    if df.empty:
        return df

    # Keep booking IDs as clean sequential values: 1,2,3,...
    normalized_ids = [str(i) for i in range(1, len(df) + 1)]
    if "ID" not in df.columns:
        df["ID"] = normalized_ids
        save_bookings(df)
        return df

    current_ids = df["ID"].fillna("").astype(str).str.strip().tolist()
    if current_ids != normalized_ids:
        df["ID"] = normalized_ids
        save_bookings(df)

    return df

def save_bookings(df):
    write_table_df(BOOKINGS_TABLE, df)

def load_inventory():
    df = read_table_df(INVENTORY_TABLE)
    if not df.empty:
        return df
    return DEFAULT_INVENTORY_DF.copy()

def save_inventory(df):
    write_table_df(INVENTORY_TABLE, df)

ensure_sqlite_storage()

def _to_float(value, default=0.0):
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)

def normalize_canadian_phone(value):
    # Accept NANP numbers for Canada with optional leading +1/1 and normalize to +1XXXXXXXXXX.
    digits = re.sub(r"\D", "", str(value or ""))

    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        return None

    # NANP constraints: area code and central office code cannot start with 0 or 1.
    if not re.fullmatch(r"[2-9]\d{2}[2-9]\d{6}", digits):
        return None

    return f"+1{digits}"

def calculate_quotation(distance_km, property_size, truck_type, cost_config):
    distance = _to_float(distance_km, 0)
    labour_rate = _to_float(cost_config.get("Labour_per_km", 0.2), 0.2)
    profit_rate = _to_float(cost_config.get("Profit_per_km", 2), 2)
    packing_cost = _to_float(cost_config.get(f"{property_size}_packing", 50), 50)
    fuel_price = _to_float(cost_config.get("Fuel_price_per_litre", 1.5), 1.5)

    mileage_key = f"{truck_type}_mileage"
    truck_mileage = _to_float(cost_config.get(mileage_key, 8), 8)
    if truck_mileage <= 0:
        truck_mileage = 8

    fuel_cost = round((distance / truck_mileage) * fuel_price, 2)
    labour_cost = round(distance * labour_rate, 2)
    profit = round(distance * profit_rate, 2)
    total_cost = round(fuel_cost + labour_cost + packing_cost + profit, 2)

    return {
        "Fuel Cost": fuel_cost,
        "Labour Cost": labour_cost,
        "Packing Cost": round(packing_cost, 2),
        "Profit": profit,
        "Total Cost": total_cost,
    }

def validate_booking_form(form_data):
    cleaned = {
        "name": str(form_data.get("name", "")).strip(),
        "phone": str(form_data.get("phone", "")).strip(),
        "email": str(form_data.get("email", "")).strip(),
        "pickup": str(form_data.get("pickup", "")).strip(),
        "drop": str(form_data.get("drop", "")).strip(),
        "property_size": str(form_data.get("property_size", "")).strip(),
        "shipment_date": str(form_data.get("shipment_date", "")).strip(),
    }

    field_errors = {}

    # Required fields
    for key, label in [
        ("name", "Full name"),
        ("phone", "Phone number"),
        ("email", "Email address"),
        ("pickup", "Pickup location"),
        ("drop", "Drop location"),
        ("property_size", "Property size"),
        ("shipment_date", "Shipment date"),
    ]:
        if not cleaned[key]:
            field_errors[key] = f"{label} is required."

    # Name validation
    if cleaned["name"] and "name" not in field_errors:
        if len(cleaned["name"]) < 2 or len(cleaned["name"]) > 80:
            field_errors["name"] = "Full name must be between 2 and 80 characters."
        elif not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", cleaned["name"]):
            field_errors["name"] = "Full name contains invalid characters."

    # Email validation
    if cleaned["email"] and "email" not in field_errors:
        if len(cleaned["email"]) > 254:
            field_errors["email"] = "Email address is too long."
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned["email"]):
            field_errors["email"] = "Please enter a valid email address."

    # Phone validation
    if cleaned["phone"] and "phone" not in field_errors:
        normalized_phone = normalize_canadian_phone(cleaned["phone"])
        if normalized_phone is None:
            field_errors["phone"] = "Please enter a valid Canadian phone number (e.g., +1 416-555-1234)."
        else:
            cleaned["phone"] = normalized_phone

    # Pickup/drop validation
    if cleaned["pickup"] and cleaned["pickup"] not in CITY_OPTIONS:
        field_errors["pickup"] = "Pickup location is invalid."
    if cleaned["drop"] and cleaned["drop"] not in CITY_OPTIONS:
        field_errors["drop"] = "Drop location is invalid."
    if cleaned["pickup"] and cleaned["drop"] and cleaned["pickup"] == cleaned["drop"]:
        field_errors["drop"] = "Pickup and drop locations must be different."

    if cleaned["property_size"] and cleaned["property_size"] not in PROPERTY_TRUCK_MAPPING:
        field_errors["property_size"] = "Property size is invalid."

    if cleaned["shipment_date"]:
        try:
            selected_date = datetime.strptime(cleaned["shipment_date"], "%Y-%m-%d").date()
            min_allowed_date = datetime.now().date() + timedelta(days=3)
            if selected_date < min_allowed_date:
                field_errors["shipment_date"] = "Shipment date must be at least 3 days from today."
        except ValueError:
            field_errors["shipment_date"] = "Shipment date format is invalid."

    return cleaned, field_errors

def parse_numeric_booking_id(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    text = str(value).strip()
    if not text:
        return None

    # Handle Excel-style numeric values like 3.0
    if re.fullmatch(r"\d+\.0+", text):
        return int(float(text))

    if text.isdigit():
        return int(text)

    return None

def get_next_booking_id(existing_bookings_df):
    if existing_bookings_df.empty or "ID" not in existing_bookings_df.columns:
        return "1"

    numeric_ids = [
        parse_numeric_booking_id(v)
        for v in existing_bookings_df["ID"].tolist()
    ]
    numeric_ids = [n for n in numeric_ids if n is not None]

    # Continue true sequential IDs if existing values already look like 1..N.
    unique_sorted = sorted(set(numeric_ids))
    if unique_sorted and unique_sorted == list(range(1, len(unique_sorted) + 1)):
        return str(unique_sorted[-1] + 1)

    # Fallback for legacy/mixed IDs: use booking count + 1.
    return str(len(existing_bookings_df) + 1)

def get_admin_filters():
    return {
        "search": request.args.get("search", "").strip(),
        "status": request.args.get("status", "all").strip().lower(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }

def filter_admin_bookings(bookings_df, admin_filters):
    filtered_df = bookings_df.copy()

    if filtered_df.empty:
        return filtered_df

    if admin_filters["status"] and admin_filters["status"] != "all" and "Status" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Status"].astype(str).str.lower() == admin_filters["status"]]

    if admin_filters["search"]:
        search_value = admin_filters["search"].lower()
        searchable_columns = [
            "ID",
            "Name",
            "Phone",
            "Email",
            "Pickup",
            "Drop",
            "Property Size",
            "Truck Assigned",
            "Status",
            "Shipment Date",
            "Booking Time",
        ]

        matching_mask = pd.Series(False, index=filtered_df.index)
        for column in searchable_columns:
            if column in filtered_df.columns:
                matching_mask = matching_mask | filtered_df[column].astype(str).str.lower().str.contains(search_value, na=False)
        filtered_df = filtered_df[matching_mask]

    if admin_filters["date_from"] or admin_filters["date_to"]:
        shipment_dates = pd.to_datetime(filtered_df.get("Shipment Date"), errors="coerce")

        if admin_filters["date_from"]:
            start_date = pd.to_datetime(admin_filters["date_from"], errors="coerce")
            if pd.notna(start_date):
                filtered_df = filtered_df[shipment_dates >= start_date]

        if admin_filters["date_to"]:
            end_date = pd.to_datetime(admin_filters["date_to"], errors="coerce")
            if pd.notna(end_date):
                filtered_df = filtered_df[shipment_dates <= end_date + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)]

    return filtered_df

def build_admin_redirect_url(admin_filters):
    redirect_args = {key: value for key, value in admin_filters.items() if value and value != "all"}
    return url_for("admin", **redirect_args)

# ----- auth -----
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["logged_in"] = True
            # Redirect to the 'admin' endpoint
            return redirect(url_for("admin"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    # Redirect to the 'login' endpoint
    return redirect(url_for("login"))

# ----- customer pages -----

# NEW: Home page route (endpoint is 'home')
@app.route("/")
def home():
    return render_template("home.html")

# UPDATED: Form page route (endpoint is 'form')
@app.route("/form")
def form():
    return render_template(
        "form.html",
        message=None,
        field_errors={},
        form_data={},
        city_options=CITY_OPTIONS,
        property_options=list(PROPERTY_TRUCK_MAPPING.keys()),
    )

@app.route("/book", methods=["POST"])
def book():
    form_data = {
        "name": request.form.get("name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": request.form.get("email", "").strip(),
        "pickup": request.form.get("pickup", "").strip(),
        "drop": request.form.get("drop", "").strip(),
        "property_size": request.form.get("property_size", "").strip(),
        "shipment_date": request.form.get("shipment_date", "").strip(),
    }

    try:
        cleaned, field_errors = validate_booking_form(form_data)
        if field_errors:
            return render_template(
                "form.html",
                message=None,
                field_errors=field_errors,
                form_data=form_data,
                city_options=CITY_OPTIONS,
                property_options=list(PROPERTY_TRUCK_MAPPING.keys()),
            )

        existing_bookings = load_bookings()

        name = cleaned["name"]
        phone = cleaned["phone"]
        email = cleaned["email"]
        pickup = cleaned["pickup"]
        drop = cleaned["drop"]
        property_size = cleaned["property_size"]
        shipment_date = cleaned["shipment_date"]
        booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        booking_id = get_next_booking_id(existing_bookings)

        distance_km, duration_min = calculate_distance_duration(pickup, drop)
        preferred_truck = PROPERTY_TRUCK_MAPPING.get(property_size, "Tata Ace")
        truck_assigned = "Pending"
        booking_status = "Pending"

        # Auto-assign by preference order: preferred, larger trucks, then smaller trucks.
        inventory_df = load_inventory()
        assignment_candidates = []
        if preferred_truck in TRUCK_CAPACITY_ORDER:
            preferred_idx = TRUCK_CAPACITY_ORDER.index(preferred_truck)
            larger = TRUCK_CAPACITY_ORDER[preferred_idx + 1:]
            smaller = list(reversed(TRUCK_CAPACITY_ORDER[:preferred_idx]))
            assignment_candidates = [preferred_truck] + larger + smaller
        else:
            assignment_candidates = TRUCK_CAPACITY_ORDER[:]

        for candidate_truck in assignment_candidates:
            truck_row = inventory_df[inventory_df["Truck Type"] == candidate_truck]
            if truck_row.empty:
                continue

            available_count = int(truck_row.iloc[0]["Available"])
            if available_count > 0:
                inventory_df.loc[inventory_df["Truck Type"] == candidate_truck, "Available"] = available_count - 1
                truck_assigned = candidate_truck
                booking_status = "Assigned"
                break

        # Load cost config and calculate quotation
        cost_config = load_cost_config()
        mileage_truck = truck_assigned if booking_status == "Assigned" else preferred_truck
        quotation = calculate_quotation(distance_km, property_size, mileage_truck, cost_config)

        entry = {
            "ID": booking_id,
            "Name": name,
            "Phone": phone,
            "Email": email,
            "Pickup": pickup,
            "Drop": drop,
            "Property Size": property_size,
            "Shipment Date": shipment_date,
            "Truck Assigned": truck_assigned,
            "Distance (km)": distance_km,
            "Duration (min)": duration_min,
            "Fuel Cost": quotation["Fuel Cost"],
            "Labour Cost": quotation["Labour Cost"],
            "Packing Cost": quotation["Packing Cost"],
            "Profit": quotation["Profit"],
            "Total Cost": quotation["Total Cost"],
            "Status": booking_status,
            "Booking Time": booking_time
        }

        existing_bookings = pd.concat([existing_bookings, pd.DataFrame([entry])], ignore_index=True)
        save_bookings(existing_bookings)
        save_inventory(inventory_df)

        if booking_status == "Assigned" and truck_assigned == preferred_truck:
            message = f"Booking successful! Estimated Cost: ${quotation['Total Cost']}. Assigned Truck: {truck_assigned}."
        elif booking_status == "Assigned":
            message = (
                f"Booking successful! Estimated Cost: ${quotation['Total Cost']}. "
                f"Preferred truck ({preferred_truck}) was unavailable, assigned {truck_assigned} instead."
            )
        else:
            message = (
                f"Booking successful! Estimated Cost: ${quotation['Total Cost']}. "
                "No truck is currently available, status is Pending."
            )

        return render_template(
            "form.html",
            message=message,
            field_errors={},
            form_data={},
            city_options=CITY_OPTIONS,
            property_options=list(PROPERTY_TRUCK_MAPPING.keys()),
        )
    except Exception as e:
        print("Booking error:", e)
        return render_template(
            "form.html",
            message=f"An error occurred: {e}",
            field_errors={},
            form_data=form_data,
            city_options=CITY_OPTIONS,
            property_options=list(PROPERTY_TRUCK_MAPPING.keys()),
        )

# ----- admin -----
@app.route("/admin")
@login_required
def admin():
    admin_filters = get_admin_filters()
    bookings_df = load_bookings()
    inventory_df = load_inventory()

    if not bookings_df.empty and "ID" in bookings_df.columns:
        bookings_df["_numeric_id"] = bookings_df["ID"].apply(parse_numeric_booking_id)
        bookings_df = bookings_df.sort_values(by=["_numeric_id", "ID"], na_position="last").drop(columns=["_numeric_id"])

    # Ensure quotation fields are consistently available and up to date in admin view.
    if not bookings_df.empty:
        cost_config = load_cost_config()
        for idx, row in bookings_df.iterrows():
            property_size = row.get("Property Size", "")
            preferred = PROPERTY_TRUCK_MAPPING.get(str(property_size), "Tata Ace")
            assigned = row.get("Truck Assigned", "Pending")
            quote_truck = assigned if assigned and assigned != "Pending" else preferred
            quotation = calculate_quotation(row.get("Distance (km)", 0), property_size, quote_truck, cost_config)
            bookings_df.at[idx, "Fuel Cost"] = quotation["Fuel Cost"]
            bookings_df.at[idx, "Labour Cost"] = quotation["Labour Cost"]
            bookings_df.at[idx, "Packing Cost"] = quotation["Packing Cost"]
            bookings_df.at[idx, "Profit"] = quotation["Profit"]
            bookings_df.at[idx, "Total Cost"] = quotation["Total Cost"]

        save_bookings(bookings_df)

    filtered_bookings_df = filter_admin_bookings(bookings_df, admin_filters)

    total_bookings = int(len(bookings_df))
    completed_bookings = 0
    pending_bookings = 0
    total_profit = 0.0

    if total_bookings > 0:
        status_series = bookings_df.get("Status", pd.Series(dtype=object)).astype(str)
        completed_bookings = int((status_series == "Completed").sum())
        pending_bookings = int((status_series == "Pending").sum())

        total_profit = float(bookings_df.get("Profit", pd.Series(dtype=float)).apply(_to_float).sum())

    analytics = {
        "total_bookings": total_bookings,
        "completed_bookings": completed_bookings,
        "pending_bookings": pending_bookings,
        "total_profit": round(total_profit, 2),
    }

    filtered_analytics = {
        "displayed_bookings": int(len(filtered_bookings_df)),
        "active_filter_count": sum(1 for key, value in admin_filters.items() if value and value != "all"),
    }
    active_query_filters = {key: value for key, value in admin_filters.items() if value and value != "all"}

    return render_template("admin.html",
                           bookings=filtered_bookings_df.to_dict(orient="records"),
                           inventory=inventory_df.to_dict(orient="records"),
                           analytics=analytics,
                           filtered_analytics=filtered_analytics,
                           active_filters=admin_filters,
                           active_query_filters=active_query_filters)

# Manual truck assignment/editing
@app.route("/assign_truck", methods=["POST"])
@login_required
def assign_truck_manual():
    booking_id = request.form.get("booking_id")
    new_truck = request.form.get("truck_type")
    admin_filters = {
        "search": request.args.get("search", "").strip(),
        "status": request.args.get("status", "all").strip().lower(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    df = load_bookings()
    inventory = load_inventory()

    idx = df[df["ID"] == booking_id].index
    if idx.empty:
        return redirect(url_for("admin"))

    current = df.at[idx[0], "Truck Assigned"]

    # No-op if the selected truck is already assigned to this booking.
    if current == new_truck:
        return redirect(url_for("admin"))

    if current and current != "Pending" and current != new_truck:
        inventory.loc[inventory["Truck Type"] == current, "Available"] += 1

    if new_truck != "Pending":
        available = inventory.loc[inventory["Truck Type"] == new_truck, "Available"].values[0]
        if available <= 0:
            return redirect(url_for("admin"))
        inventory.loc[inventory["Truck Type"] == new_truck, "Available"] -= 1

    df.at[idx[0], "Truck Assigned"] = new_truck
    df.at[idx[0], "Status"] = "Assigned" if new_truck != "Pending" else "Pending"

    # Recalculate quotation values based on current assignment.
    row = df.loc[idx[0]]
    property_size = row.get("Property Size", "")
    preferred = PROPERTY_TRUCK_MAPPING.get(str(property_size), "Tata Ace")
    quote_truck = new_truck if new_truck != "Pending" else preferred
    quotation = calculate_quotation(row.get("Distance (km)", 0), property_size, quote_truck, load_cost_config())
    df.at[idx[0], "Fuel Cost"] = quotation["Fuel Cost"]
    df.at[idx[0], "Labour Cost"] = quotation["Labour Cost"]
    df.at[idx[0], "Packing Cost"] = quotation["Packing Cost"]
    df.at[idx[0], "Profit"] = quotation["Profit"]
    df.at[idx[0], "Total Cost"] = quotation["Total Cost"]

    save_inventory(inventory)
    save_bookings(df)
    return redirect(build_admin_redirect_url(admin_filters))

# Mark as completed (returns truck)
@app.route("/complete/<booking_id>")
@login_required
def complete_delivery(booking_id):
    admin_filters = {
        "search": request.args.get("search", "").strip(),
        "status": request.args.get("status", "all").strip().lower(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    df = load_bookings()
    inventory = load_inventory()
    idx = df[df["ID"] == booking_id].index
    if not idx.empty:
        truck_type = df.at[idx[0], "Truck Assigned"]
        df.at[idx[0], "Status"] = "Completed"
        if truck_type and truck_type != "Pending":
            inventory.loc[inventory["Truck Type"] == truck_type, "Available"] += 1
        save_inventory(inventory)
        save_bookings(df)
    return redirect(build_admin_redirect_url(admin_filters))

# Export endpoints
@app.route("/export/bookings")
@login_required
def export_bookings():
    df = load_bookings()
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="bookings.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/export/inventory")
@login_required
def export_inventory():
    df = load_inventory()
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="inventory.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == '__main__':
    app.run(debug=True)


