# 🚚 Transport Booking Website

A Flask-based web application developed to streamline transportation booking and fleet management for a moving company. The system automates customer bookings, truck allocation, quotation generation, route calculation, and booking management through an intuitive admin dashboard.

The project was developed as part of an internship for **TrueNorth Van Lines** to improve operational efficiency by digitizing the complete booking workflow.

---

## 🌐 Live Demo

🔗 [https://truemnorthvanlines.up.railway.app](https://truemnorthvanlines.up.railway.app)

---

## 📌 Project Overview

The Transport Booking Website enables customers to book transportation services online while allowing administrators to efficiently manage bookings, truck inventory, and delivery status.

The application automatically assigns trucks based on the customer's property size, calculates travel distance and estimated duration using the OpenRouteService API, and provides administrators with tools to monitor bookings and manage transportation resources effectively.

---

## ✨ Features

### 👤 Customer Module

- Online transport booking form
- Pickup and drop location entry
- Property size selection
- Automatic truck assignment
- Automatic quotation generation
- Distance and travel duration calculation
- Booking confirmation

---

### 👨‍💼 Admin Module

- Secure admin login
- View all customer bookings
- Edit booking details
- Delete bookings
- Mark deliveries as completed
- Download booking records to Excel
- Filter bookings by shipment date

---

### 🚛 Truck Inventory Management

- Automatic truck allocation
- Inventory tracking
- Automatic availability updates after delivery completion
- Multiple truck categories supported

---

### 📍 Route Optimization

- OpenRouteService API integration
- Automatic distance calculation
- Estimated travel duration
- Optimized driving routes

---

## 🛠️ Technologies Used

### Backend

- Python
- Flask

### Frontend

- HTML5
- CSS3
- JavaScript

### Database

- SQLite

### Libraries

- Pandas
- OpenPyXL
- OpenRouteService
- Gunicorn

### Deployment

- Railway

---

## 📂 Project Structure

```text
Transport-booking-website/
│
├── app.py
├── wsgi.py
├── requirements.txt
├── Procfile
├── railway.json
├── .python-version
├── transport_booking.sqlite
├── truck_inventory.xlsx
├── customer_bookings.xlsx
│
├── templates/
│   ├── home.html
│   ├── form.html
│   ├── login.html
│   ├── admin.html
│   ├── edit.html
│   └── truck_inventory.html
│
├── static/
│
└── README.md
```

---

## ⚙️ Installation

### Clone the repository

```bash
git clone https://github.com/keerthivasan18-7/Transport-booking-website-.git
```

Move into the project directory

```bash
cd Transport-booking-website-
```

---

### Create a virtual environment

Windows

```bash
python -m venv .venv
```

Activate

```bash
.\.venv\Scripts\activate
```

---

### Install dependencies

```bash
pip install -r requirements.txt
```

---

### Configure Environment Variables

Create a `.env` file or configure the following variables:

```text
FLASK_SECRET_KEY=your_secret_key
ADMIN_USER=admin
ADMIN_PASS=your_password
ORS_API_KEY=your_openrouteservice_api_key
```

---

### Run the application

```bash
python app.py
```

The application will be available at:

```text
http://127.0.0.1:5000
```

---

## 🚀 Deployment

This project has been deployed on **Railway** using Gunicorn.

Production Start Command:

```bash
gunicorn --bind 0.0.0.0:$PORT wsgi:application
```

Production URL:

```text
https://truemnorthvanlines.up.railway.app
```

---

## 📊 Key Functionalities

- Customer booking management
- Vehicle allocation automation
- Distance calculation
- Travel time estimation
- Route optimization
- Truck inventory management
- Admin dashboard
- Excel export
- Booking status management

---

## 📸 Screenshots

Add screenshots of:

- Home Page
- Booking Form
- Admin Dashboard
- Truck Inventory
- Booking Records

Example:

```text
screenshots/
    home.png
    dashboard.png
    inventory.png
```

---

## 🔮 Future Enhancements

- PostgreSQL database integration
- Google Maps integration
- Email confirmation for bookings
- SMS notifications
- Live GPS tracking
- Customer booking history
- Online payment gateway
- Multi-admin support
- Analytics dashboard
- Driver management module

---

## 👨‍💻 Developed By

**A. Keerthivasan**

B.Tech Computer Science and Engineering (Artificial Intelligence & Machine Learning)

SRM Institute of Science and Technology

GitHub:
https://github.com/keerthivasan18-7

LinkedIn: www.linkedin.com/in/keerthivasan-a-0195392a4


---

## 📄 License

This project was developed for educational and internship purposes.

© 2026 A. Keerthivasan. All rights reserved.
