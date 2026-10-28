from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "apollo_hms_2025"

def get_db():
    return mysql.connector.connect(
        host="localhost", user="root", password="uday", database="covid"
    )

# ════════════════════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════════════════════
@app.route("/")
def home():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS c FROM hospitaldata"); h = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM bookingpatient"); p = cur.fetchone()["c"]
    try:
        cur.execute("SELECT COUNT(*) AS c FROM doctors"); d = cur.fetchone()["c"]
    except: d = 0
    try:
        cur.execute("SELECT COUNT(*) AS c FROM consultations"); c = cur.fetchone()["c"]
    except: c = 0
    cur.close(); db.close()
    return render_template("home.html", stat_hospitals=h, stat_patients=p, stat_doctors=d, stat_consult=c)

# ════════════════════════════════════════════════════════════
#  PATIENT
# ════════════════════════════════════════════════════════════
@app.route("/patient/register", methods=["GET","POST"])
def patient_register():
    if request.method == "POST":
        try:
            db = get_db(); cur = db.cursor()
            cur.execute(
                "INSERT INTO user (srfid,email,dob,pname,pphone,hcode) VALUES (%s,%s,%s,%s,%s,%s)",
                (request.form["srfid"], request.form["email"], request.form["dob"],
                 request.form["pname"], request.form["pphone"], request.form.get("hcode",""))
            )
            db.commit(); cur.close(); db.close()
            flash("Account created! Please login.", "success")
            return redirect(url_for("patient_login"))
        except mysql.connector.Error as e:
            flash(f"Error: {e}", "error")
    return render_template("patient_register.html")

@app.route("/patient/login", methods=["GET","POST"])
def patient_login():
    if request.method == "POST":
        try:
            db = get_db(); cur = db.cursor(dictionary=True)
            cur.execute("SELECT * FROM user WHERE srfid=%s AND dob=%s",
                        (request.form["srfid"], request.form["dob"]))
            u = cur.fetchone(); cur.close(); db.close()
            if u:
                session.update({"patient": u["srfid"], "patient_id": u["id"],
                                "patient_name": u.get("pname", u["srfid"])})
                return redirect(url_for("patient_dashboard"))
            flash("Invalid SRF ID or Date of Birth.", "error")
        except mysql.connector.Error as e:
            flash(f"Error: {e}", "error")
    return render_template("patient_login.html")

@app.route("/patient/logout")
def patient_logout():
    [session.pop(k, None) for k in ["patient","patient_id","patient_name"]]
    return redirect(url_for("home"))

@app.route("/patient/dashboard")
def patient_dashboard():
    if "patient" not in session: return redirect(url_for("patient_login"))
    srfid = session["patient"]
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM bookingpatient WHERE srfid=%s", (srfid,))
    bookings = cur.fetchall()
    cur.execute("SELECT hcode, hname FROM hospitaldata")
    hospitals = cur.fetchall()
    try:
        cur.execute("""SELECT c.*, d.name AS doc_name, d.specialization
                       FROM consultations c JOIN doctors d ON c.doctor_id=d.id
                       WHERE c.srfid=%s ORDER BY c.id DESC""", (srfid,))
        consults = cur.fetchall()
    except: consults = []
    try:
        cur.execute("SELECT * FROM doctors WHERE status='available' ORDER BY specialization")
        doctors = cur.fetchall()
    except: doctors = []
    cur.close(); db.close()
    return render_template("patient_dashboard.html",
                           bookings=bookings, hospitals=hospitals,
                           consults=consults, doctors=doctors)

@app.route("/patient/book", methods=["POST"])
def patient_book():
    if "patient" not in session: return redirect(url_for("patient_login"))
    srfid = session["patient"]
    bedtype  = request.form["bedtype"]
    hcode    = request.form["hcode"]
    spo2     = request.form["spo2"]
    pphone   = request.form["pphone"]
    paddress = request.form["paddress"]

    # Map bed type to column name
    bed_col_map = {
        "Normal Bed":      "normalbed",
        "HICU Bed":        "hicubed",
        "ICU Bed":         "icubed",
        "Ventilator Bed":  "vbed"
    }
    bed_col = bed_col_map.get(bedtype)

    try:
        db = get_db(); cur = db.cursor(dictionary=True)

        # Check already booked
        cur.execute("SELECT id FROM bookingpatient WHERE srfid=%s", (srfid,))
        if cur.fetchone():
            flash("You already have an active bed booking.", "error")
            cur.close(); db.close()
            return redirect(url_for("patient_dashboard"))

        # Check bed availability
        cur.execute(f"SELECT {bed_col} FROM hospitaldata WHERE hcode=%s", (hcode,))
        row = cur.fetchone()
        if not row or row[bed_col] <= 0:
            flash(f"No {bedtype}s available at this hospital.", "error")
            cur.close(); db.close()
            return redirect(url_for("patient_dashboard"))

        # Insert booking
        cur = db.cursor()
        cur.execute(
            "INSERT INTO bookingpatient (srfid,bedtype,hcode,spo2,pname,pphone,paddress) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (srfid, bedtype, hcode, spo2, session.get("patient_name",""), pphone, paddress)
        )

        # Reduce bed count by 1
        cur.execute(f"UPDATE hospitaldata SET {bed_col} = {bed_col} - 1 WHERE hcode=%s", (hcode,))

        db.commit()
        flash("Bed booked successfully!", "success")
        cur.close(); db.close()

    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("patient_dashboard"))

@app.route("/patient/cancel/<int:bid>", methods=["POST"])
def patient_cancel(bid):
    if "patient" not in session: return redirect(url_for("patient_login"))
    bed_col_map = {
        "Normal Bed":     "normalbed",
        "HICU Bed":       "hicubed",
        "ICU Bed":        "icubed",
        "Ventilator Bed": "vbed"
    }
    try:
        db = get_db(); cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM bookingpatient WHERE id=%s AND srfid=%s", (bid, session["patient"]))
        booking = cur.fetchone()
        if booking:
            bed_col = bed_col_map.get(booking["bedtype"])
            cur = db.cursor()
            cur.execute("DELETE FROM bookingpatient WHERE id=%s", (bid,))
            # Add bed back
            if bed_col:
                cur.execute(f"UPDATE hospitaldata SET {bed_col} = {bed_col} + 1 WHERE hcode=%s", (booking["hcode"],))
            db.commit()
            flash("Booking cancelled and bed returned.", "success")
        cur.close(); db.close()
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("patient_dashboard"))

@app.route("/patient/consult", methods=["POST"])
def patient_consult():
    if "patient" not in session: return redirect(url_for("patient_login"))
    try:
        db = get_db(); cur = db.cursor()
        cur.execute(
            "INSERT INTO consultations (srfid,doctor_id,disease,description,status) VALUES (%s,%s,%s,%s,'pending')",
            (session["patient"], request.form["doctor_id"],
             request.form["disease"], request.form["description"])
        )
        db.commit(); cur.close(); db.close()
        flash("Consultation request sent to doctor!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("patient_dashboard"))

# ════════════════════════════════════════════════════════════
#  HOSPITAL
# ════════════════════════════════════════════════════════════
@app.route("/hospital/register", methods=["GET","POST"])
def hospital_register():
    if request.method == "POST":
        try:
            db = get_db(); cur = db.cursor()
            cur.execute("INSERT INTO hospitaluser (hcode,email,password) VALUES (%s,%s,%s)",
                        (request.form["hcode"], request.form["email"], request.form["password"]))
            cur.execute("INSERT INTO hospitaldata (hcode,hname,normalbed,hicubed,icubed,vbed) VALUES (%s,%s,%s,%s,%s,%s)",
                        (request.form["hcode"], request.form["hname"],
                         request.form["normalbed"], request.form["hicubed"],
                         request.form["icubed"], request.form["vbed"]))
            db.commit(); cur.close(); db.close()
            flash("Hospital registered! Please login.", "success")
            return redirect(url_for("hospital_login"))
        except mysql.connector.Error as e:
            flash(f"Error: {e}", "error")
    return render_template("hospital_register.html")

@app.route("/hospital/login", methods=["GET","POST"])
def hospital_login():
    if request.method == "POST":
        try:
            db = get_db(); cur = db.cursor(dictionary=True)
            cur.execute("SELECT * FROM hospitaluser WHERE hcode=%s AND email=%s",
                        (request.form["hcode"], request.form["email"]))
            hu = cur.fetchone(); cur.close(); db.close()
            if hu and hu["password"] == request.form["password"]:
                session["hospital"] = hu["hcode"]
                return redirect(url_for("hospital_dashboard"))
            flash("Invalid credentials.", "error")
        except mysql.connector.Error as e:
            flash(f"Error: {e}", "error")
    return render_template("hospital_login.html")

@app.route("/hospital/logout")
def hospital_logout():
    [session.pop(k, None) for k in ["hospital"]]
    return redirect(url_for("home"))

@app.route("/hospital/dashboard")
def hospital_dashboard():
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    hcode = session["hospital"]
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM bookingpatient WHERE hcode=%s", (hcode,))
    patients = cur.fetchall()
    cur.execute("SELECT * FROM hospitaldata WHERE hcode=%s", (hcode,))
    hdata = cur.fetchone()
    try:
        cur.execute("SELECT * FROM doctors WHERE hcode=%s", (hcode,))
        doctors = cur.fetchall()
        cur.execute("""SELECT c.*, d.name AS doc_name, d.specialization
                       FROM consultations c JOIN doctors d ON c.doctor_id=d.id
                       WHERE d.hcode=%s ORDER BY c.id DESC""", (hcode,))
        consults = cur.fetchall()
    except: doctors = []; consults = []
    cur.close(); db.close()
    return render_template("hospital_dashboard.html",
                           patients=patients, hdata=hdata,
                           doctors=doctors, consults=consults)

@app.route("/hospital/update_beds", methods=["POST"])
def hospital_update_beds():
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("UPDATE hospitaldata SET normalbed=%s,hicubed=%s,icubed=%s,vbed=%s WHERE hcode=%s",
                    (request.form["normalbed"], request.form["hicubed"],
                     request.form["icubed"], request.form["vbed"], session["hospital"]))
        db.commit(); cur.close(); db.close()
        flash("Bed counts updated!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hospital_dashboard"))

@app.route("/hospital/discharge/<int:bid>", methods=["POST"])
def hospital_discharge(bid):
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    bed_col_map = {
        "Normal Bed":     "normalbed",
        "HICU Bed":       "hicubed",
        "ICU Bed":        "icubed",
        "Ventilator Bed": "vbed"
    }
    try:
        db = get_db(); cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM bookingpatient WHERE id=%s AND hcode=%s", (bid, session["hospital"]))
        booking = cur.fetchone()
        if booking:
            bed_col = bed_col_map.get(booking["bedtype"])
            cur = db.cursor()
            cur.execute("DELETE FROM bookingpatient WHERE id=%s", (bid,))
            if bed_col:
                cur.execute(f"UPDATE hospitaldata SET {bed_col} = {bed_col} + 1 WHERE hcode=%s", (booking["hcode"],))
            db.commit()
            flash("Patient discharged and bed restored.", "success")
        cur.close(); db.close()
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hospital_dashboard"))

@app.route("/hospital/add_doctor", methods=["POST"])
def hospital_add_doctor():
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    try:
        db = get_db(); cur = db.cursor()
        cur.execute(
            "INSERT INTO doctors (hcode,name,specialization,email,phone,status) VALUES (%s,%s,%s,%s,%s,'available')",
            (session["hospital"], request.form["name"], request.form["specialization"],
             request.form["email"], request.form["phone"])
        )
        db.commit(); cur.close(); db.close()
        flash("Doctor added successfully!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hospital_dashboard"))

@app.route("/hospital/remove_doctor/<int:did>", methods=["POST"])
def hospital_remove_doctor(did):
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("DELETE FROM doctors WHERE id=%s AND hcode=%s", (did, session["hospital"]))
        db.commit(); cur.close(); db.close()
        flash("Doctor removed.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hospital_dashboard"))

@app.route("/hospital/update_consult/<int:cid>", methods=["POST"])
def hospital_update_consult(cid):
    if "hospital" not in session: return redirect(url_for("hospital_login"))
    try:
        db = get_db(); cur = db.cursor()
        cur.execute("UPDATE consultations SET status=%s, prescription=%s WHERE id=%s",
                    (request.form["status"], request.form["prescription"], cid))
        db.commit(); cur.close(); db.close()
        flash("Consultation updated!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("hospital_dashboard"))

@app.route("/hospitals")
def hospitals():
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM hospitaldata")
    rows = cur.fetchall()
    cur.close(); db.close()
    return render_template("hospitals.html", hospitals=rows)

if __name__ == "__main__":
    app.run(debug=True)

