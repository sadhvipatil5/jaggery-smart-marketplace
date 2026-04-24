class Config:
    SECRET_KEY = 'mysecretkey123'
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:admin123@localhost/gud'  # Update with your PostgreSQL credentials
    SQLALCHEMY_TRACK_MODIFICATIONS = False
