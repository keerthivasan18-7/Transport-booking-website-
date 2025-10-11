from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import os
from datetime import datetime
import uuid
import io
import openrouteservice
from functools import wraps

app = Flask(__name__)
# NOTE: It's HIGHLY recommended to load secret keys from environment variables, not hardcode them.
app.secret_key = "5b3ce3597851110001cf6248cb6a989066ed40e19314e88c13df2bfb"

# Replace with your actual ORS key
ORS_API_KEY = "5b3ce3597851110001cf6248cb6a989066ed40e19314e88c13df2bfb"
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# File paths
DATA_FILE = "customer_data.xlsx"
INVENTORY_FILE = "truck_inventory.xlsx"
COST_FILE = "cost_config.xlsx"

# Admin credentials
ADMIN_USER = "admin"
ADMIN_PASS = "password123"

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
    "5 Rooms": "BharatBenz 3123"
}

# Ensure inventory file exists
if not os.path.exists(INVENTORY_FILE):
    pd.DataFrame(list(DEFAULT_INVENTORY.items()), columns=["Truck Type", "Available"]).to_excel(INVENTORY_FILE, index=False)

# ----- helpers -----
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            # Redirect to the 'login' endpoint
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def load_cost_config():
    if os.path.exists(COST_FILE):
        return pd.read_excel(COST_FILE, index_col=0).to_dict()['Value']
    return {
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
        "5 Rooms_packing": 120
    }

def calculate_distance_duration(pickup, drop):
    try:
        # NOTE: geocode and ors_client require accurate setup and API key which is assumed here.
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
    if os.path.exists(DATA_FILE):
        return pd.read_excel(DATA_FILE)
    return pd.DataFrame()

def save_bookings(df):
    df.to_excel(DATA_FILE, index=False)

def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        return pd.read_excel(INVENTORY_FILE)
    return pd.DataFrame(list(DEFAULT_INVENTORY.items()), columns=["Truck Type", "Available"])

def save_inventory(df):
    df.to_excel(INVENTORY_FILE, index=False)

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
    return render_template("form.html", message=None)

@app.route("/book", methods=["POST"])
def book():
    try:
        data = request.form
        name = data["name"]
        phone = data["phone"]
        email = data["email"]
        pickup = data["pickup"]
        drop = data["drop"]
        property_size = data["property_size"]
        shipment_date = data["shipment_date"]
        booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        booking_id = str(uuid.uuid4())[:8]

        distance_km, duration_min = calculate_distance_duration(pickup, drop)
        truck_assigned = "Pending"

        # Load cost config and calculate quotation
        cost_config = load_cost_config()
        labour_cost = distance_km * cost_config.get("Labour_per_km", 0.2)
        profit = distance_km * cost_config.get("Profit_per_km", 2)
        packing_key = f"{property_size}_packing"
        packing_cost = cost_config.get(packing_key, 50)
        preferred_truck = PROPERTY_TRUCK_MAPPING.get(property_size, "Tata Ace")
        truck_mileage_key = f"{preferred_truck}_mileage"
        truck_mileage = cost_config.get(truck_mileage_key, 8)
        fuel_price = cost_config.get("Fuel_price_per_litre", 1.5)
        fuel_cost = round((distance_km / truck_mileage) * fuel_price, 2)
        total_cost = round(fuel_cost + labour_cost + packing_cost + profit, 2)

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
            "Fuel Cost": fuel_cost,
            "Labour Cost": labour_cost,
            "Packing Cost": packing_cost,
            "Profit": profit,
            "Total Cost": total_cost,
            "Status": "Pending",
            "Booking Time": booking_time
        }

        df = load_bookings()
        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
        save_bookings(df)
        return render_template("form.html", message=f"Booking successful! Estimated Cost: ${total_cost}")
    except Exception as e:
        print("Booking error:", e)
        return render_template("form.html", message=f"An error occurred: {e}")

# ----- admin -----
@app.route("/admin")
@login_required
def admin():
    bookings_df = load_bookings()
    inventory_df = load_inventory()
    return render_template("admin.html",
                           bookings=bookings_df.to_dict(orient="records"),
                           inventory=inventory_df.to_dict(orient="records"))

# Manual truck assignment/editing
@app.route("/assign_truck", methods=["POST"])
@login_required
def assign_truck_manual():
    booking_id = request.form.get("booking_id")
    new_truck = request.form.get("truck_type")
    df = load_bookings()
    inventory = load_inventory()

    idx = df[df["ID"] == booking_id].index
    if idx.empty:
        return redirect(url_for("admin"))

    current = df.at[idx[0], "Truck Assigned"]
    if current and current != "Pending" and current != new_truck:
        inventory.loc[inventory["Truck Type"] == current, "Available"] += 1

    if new_truck != "Pending":
        available = inventory.loc[inventory["Truck Type"] == new_truck, "Available"].values[0]
        if available <= 0:
            return redirect(url_for("admin"))
        inventory.loc[inventory["Truck Type"] == new_truck, "Available"] -= 1

    df.at[idx[0], "Truck Assigned"] = new_truck
    df.at[idx[0], "Status"] = "Assigned" if new_truck != "Pending" else "Pending"

    save_inventory(inventory)
    save_bookings(df)
    return redirect(url_for("admin"))

# Mark as completed (returns truck)
@app.route("/complete/<booking_id>")
@login_required
def complete_delivery(booking_id):
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
    return redirect(url_for("admin"))

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


