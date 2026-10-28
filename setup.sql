USE covid;

-- Doctors table
CREATE TABLE IF NOT EXISTS doctors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hcode VARCHAR(50) NOT NULL,
  name VARCHAR(100) NOT NULL,
  specialization VARCHAR(100) NOT NULL,
  email VARCHAR(100),
  phone VARCHAR(15),
  status VARCHAR(20) DEFAULT 'available'
);

-- Consultations table
CREATE TABLE IF NOT EXISTS consultations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  srfid VARCHAR(50) NOT NULL,
  doctor_id INT NOT NULL,
  disease VARCHAR(100) NOT NULL,
  description TEXT,
  status VARCHAR(30) DEFAULT 'pending',
  prescription TEXT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add missing columns to user table (ignore errors if already exist)
ALTER TABLE user ADD COLUMN pname VARCHAR(100) DEFAULT '';
ALTER TABLE user ADD COLUMN pphone VARCHAR(12) DEFAULT '';
ALTER TABLE user ADD COLUMN hcode VARCHAR(50) DEFAULT '';
