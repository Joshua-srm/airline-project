from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from geopy.distance import great_circle
from datetime import datetime, timedelta
import random

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'student',
    'database': 'AIRLINE'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(query, params=None, fetch=False, commit=False):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute(query, params or ())
        if commit:
            conn.commit()
        if fetch:
            return cursor.fetchall()
        return None
    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        raise err
    finally:
        if cursor:
            if cursor.with_rows:
                try:
                    cursor.fetchall()
                except:
                    pass
            cursor.close()
        if conn:
            conn.close()

def check_db_health():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DESCRIBE AIRPORTS")
        cols = [col[0] for col in cursor.fetchall()]
        if 'Latitude' not in cols or 'Longitude' not in cols:
            print("WARNING: Missing Latitude/Longitude in AIRPORTS table")
    except Exception as e:
        print(f"DB health check error: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

app = Flask(__name__)
CORS(app)

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    correct_username = "Admin"
    correct_password = "admin123"
    if username == correct_username and password == correct_password:
        return jsonify({"message": "Login successful. Welcome to the FMS."}), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/admin/fleet', methods=['GET'])
def get_fleet_admin():
    try:
        fleet = execute_query("SELECT Reg_No, Aircraft, Passenger_Capacity, Max_Distance_miles, COALESCE(Status,'Available') AS Status FROM FLEET", fetch=True)
        return jsonify(fleet), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/destination', methods=['POST', 'DELETE'])
def manage_destination():
    try:
        data = request.json
        if request.method == 'POST':
            lat = 10.152
            lon = 76.398
            query = "INSERT INTO AIRPORTS (ICAO_Code, Airport_Name, Location, Latitude, Longitude) VALUES (%s, %s, %s, %s, %s)"
            execute_query(query, (data['icao_code'], data['airport_name'], data['location'], lat, lon), commit=True)
            return jsonify({"message": f"Destination {data['icao_code']} added successfully."}), 200
        elif request.method == 'DELETE':
            query = "DELETE FROM AIRPORTS WHERE ICAO_Code = %s"
            execute_query(query, (data['icao_code'],), commit=True)
            return jsonify({"message": f"Destination {data['icao_code']} deleted successfully."}), 200
    except mysql.connector.errors.IntegrityError:
        return jsonify({"error": "ICAO code already exists or database constraint failed."}), 400
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

@app.route('/api/admin/conduct_flight', methods=['POST'])
def conduct_flight():
    data = request.json
    reg_no = data.get('reg_no')
    arv_icao = data.get('arv_icao')
    dep_icao = 'VOCI'
    try:
        airport_data = execute_query("SELECT ICAO_Code, Airport_Name, Latitude, Longitude FROM AIRPORTS WHERE ICAO_Code IN (%s, %s)", (dep_icao, arv_icao), fetch=True)
        fleet_data = execute_query("SELECT Max_Distance_miles, Passenger_Capacity FROM FLEET WHERE Reg_No = %s", (reg_no,), fetch=True)
        if len(airport_data) != 2 or any(a['Latitude'] is None for a in airport_data):
            return jsonify({"error": "Departure or Arrival airport not found or missing coordinates."}), 404
        if not fleet_data:
            return jsonify({"error": "Aircraft not found in fleet."}), 404
        dep = next(a for a in airport_data if a['ICAO_Code'] == dep_icao)
        arv = next(a for a in airport_data if a['ICAO_Code'] == arv_icao)
        max_distance = fleet_data[0]['Max_Distance_miles']
        max_passenger = fleet_data[0]['Passenger_Capacity']
        dep_coords = (dep['Latitude'], dep['Longitude'])
        arv_coords = (arv['Latitude'], arv['Longitude'])
        flt_distance_miles = int(great_circle(dep_coords, arv_coords).miles)
        if flt_distance_miles > max_distance:
            return jsonify({"error": f"Aircraft range is too short ({max_distance} miles) for this route ({flt_distance_miles} miles)."}), 400
        rate = 15
        cost_per_passenger = int(rate * flt_distance_miles)
        passengers_to = random.randrange(max(int(max_passenger * 0.7),1), max_passenger+1)
        earnings_to = passengers_to * cost_per_passenger
        passengers_from = random.randrange(max(int(max_passenger * 0.7),1), max_passenger+1)
        earnings_from = passengers_from * cost_per_passenger
        total_earnings = earnings_to + earnings_from
        update_balance_query = "UPDATE BALANCE SET Amount = Amount + %s LIMIT 1"
        execute_query(update_balance_query, (total_earnings,), commit=True)
        return jsonify({
            "message": "Flight simulation complete.",
            "earnings": total_earnings,
            "departure": dep['Airport_Name'],
            "arrival": arv['Airport_Name'],
            "passengers_to": passengers_to,
            "passengers_from": passengers_from
        }), 200
    except Exception as e:
        return jsonify({"error": f"Flight simulation failed: {e}"}), 500

@app.route('/api/balance', methods=['GET'])
def get_balance():
    try:
        balance_data = execute_query("SELECT Amount FROM BALANCE LIMIT 1", fetch=True)
        amount = balance_data[0]['Amount'] if balance_data else 0
        return jsonify({"Amount": amount}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/airports/customer', methods=['GET'])
def get_airports_customer():
    try:
        airports = execute_query("SELECT ICAO_Code, Airport_Name, Location, Latitude, Longitude FROM AIRPORTS", fetch=True)
        return jsonify(airports), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch airports: {e}"}), 500

@app.route('/api/check_flight', methods=['POST'])
def check_flight():
    data = request.json
    dep_icao = data.get('dep_icao')
    arv_icao = data.get('arv_icao')
    try:
        airport_data = execute_query("SELECT ICAO_Code, Latitude, Longitude FROM AIRPORTS WHERE ICAO_Code IN (%s, %s)", (dep_icao, arv_icao), fetch=True)
        fleet_data = execute_query("SELECT MAX(Max_Distance_miles) as max_dist FROM FLEET", fetch=True)
        if len(airport_data) != 2 or any(a['Latitude'] is None for a in airport_data):
            return jsonify({"error": "One or both airport codes are invalid or missing coordinates. Check MySQL data."}), 404
        if not fleet_data or fleet_data[0]['max_dist'] is None:
            return jsonify({"error": "No aircraft in the fleet to support any flight."}), 404
        dep = next(a for a in airport_data if a['ICAO_Code'] == dep_icao)
        arv = next(a for a in airport_data if a['ICAO_Code'] == arv_icao)
        max_fleet_distance = fleet_data[0]['max_dist']
        dep_coords = (dep['Latitude'], dep['Longitude'])
        arv_coords = (arv['Latitude'], arv['Longitude'])
        flt_distance_miles = int(great_circle(dep_coords, arv_coords).miles)
        if flt_distance_miles > max_fleet_distance:
            return jsonify({"error": "No available aircraft can reach this destination."}), 400
        rate = 15
        base_cost = int(rate * flt_distance_miles)
        return jsonify({
            "departure": dep_icao,
            "arrival": arv_icao,
            "distance_miles": flt_distance_miles,
            "base_cost": base_cost
        }), 200
    except Exception as e:
        return jsonify({"error": f"Flight check failed: {e}"}), 500

@app.route('/api/book_ticket', methods=['POST'])
def book_ticket():
    data = request.json
    try:
        date_str = data.get('date_of_flight')
        if not date_str:
            return jsonify({"error": "date_of_flight required"}), 400
        try:
            selected = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except:
            try:
                selected = datetime.strptime(date_str, '%Y-%m-%d')
            except:
                return jsonify({"error": "Invalid date format for date_of_flight"}), 400

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if selected < today:
            return jsonify({"error": "Cannot book a flight in the past"}), 400

        tk_id = int(datetime.now().timestamp() * 1000)
        insert_query = "INSERT INTO BOOKING (TkID, Name, DEP, ARV, DOF, Cost) VALUES (%s, %s, %s, %s, %s, %s)"
        execute_query(insert_query, (tk_id, data['name'], data['dep_icao'], data['arv_icao'], date_str, data['total_cost']), commit=True)
        update_balance_query = "UPDATE BALANCE SET Amount = Amount + %s LIMIT 1"
        execute_query(update_balance_query, (data['total_cost'],), commit=True)
        return jsonify({"message": "Booking successful!", "tk_id": tk_id}), 200
    except Exception as e:
        return jsonify({"error": f"Booking failed: {e}"}), 500

@app.route('/api/bookings', methods=['GET'])
def get_customer_bookings():
    try:
        bookings = execute_query("SELECT TkID, Name, DEP, ARV, DOF, Cost FROM BOOKING ORDER BY DOF DESC", fetch=True)
        return jsonify(bookings), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cancel_booking', methods=['POST'])
def cancel_booking():
    data = request.json
    tk_id = data.get('tk_id')
    provided_cost = data.get('cost')
    provided_refund_percent = data.get('refund_percent', None)
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT DOF, Cost FROM BOOKING WHERE TkID = %s", (tk_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close(); conn.close()
            return jsonify({"error": "Booking not found."}), 404
        dof_val = row['DOF']
        booked_cost = float(row['Cost'])
        cost_to_use = float(provided_cost) if provided_cost is not None else booked_cost
        refund_percent = None
        if provided_refund_percent is not None:
            refund_percent = float(provided_refund_percent)
        else:
            if isinstance(dof_val, datetime):
                dof_dt = dof_val
            else:
                try:
                    dof_dt = datetime.strptime(str(dof_val), '%Y-%m-%d')
                except:
                    try:
                        dof_dt = datetime.strptime(str(dof_val), '%Y-%m-%d %H:%M:%S')
                    except:
                        dof_dt = datetime.strptime(str(dof_val), '%Y-%m-%d')
            now = datetime.now()
            delta = dof_dt - now
            hours = delta.total_seconds() / 3600.0
            if hours >= 48:
                refund_percent = 100.0
            elif hours >= 24:
                refund_percent = 50.0
            elif hours >= 0:
                refund_percent = 25.0
            else:
                refund_percent = 0.0
        if refund_percent < 0: refund_percent = 0.0
        if refund_percent > 100: refund_percent = 100.0
        refund_amount = (refund_percent / 100.0) * cost_to_use
        cursor.execute("DELETE FROM BOOKING WHERE TkID = %s", (tk_id,))
        conn.commit()
        cursor.execute("UPDATE BALANCE SET Amount = Amount - %s LIMIT 1", (refund_amount,))
        conn.commit()
        cursor.close(); conn.close()
        refundable = int(refund_amount) if float(refund_amount).is_integer() else refund_amount
        return jsonify({"message": f"Ticket {tk_id} cancelled. Refund processed: Rs. {refundable} ({refund_percent}%)."}), 200
    except Exception as e:
        return jsonify({"error": f"Cancellation failed: {e}"}), 500

@app.route('/api/admin/reschedule_flight', methods=['POST'])
def admin_reschedule_flight():
    data = request.json
    dep = data.get('dep')
    arv = data.get('arv')
    old_dof = data.get('old_dof')
    new_dof = data.get('new_dof')
    if not dep or not arv or not old_dof or not new_dof:
        return jsonify({"error": "dep, arv, old_dof and new_dof are required."}), 400
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        update_query = "UPDATE BOOKING SET DOF = %s WHERE DEP = %s AND ARV = %s AND DOF = %s"
        cursor.execute(update_query, (new_dof, dep, arv, old_dof))
        affected = cursor.rowcount
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"message": f"Rescheduled {affected} booking(s) from {old_dof} to {new_dof} for route {dep}->{arv}."}), 200
    except Exception as e:
        return jsonify({"error": f"Reschedule failed: {e}"}), 500

if __name__ == '__main__':
    check_db_health()
    app.run(debug=True)
