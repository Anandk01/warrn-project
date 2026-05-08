from app import app, db, User, bcrypt

def create_admin(username, password):
    with app.app_context():
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"User '{username}' already exists!")
            return
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        admin_user = User(username=username, password_hash=hashed_password, role='admin')
        db.session.add(admin_user)
        db.session.commit()
        print(f"Admin user '{username}' created successfully!")

if __name__ == '__main__':
    # Change these values to create your admin
    create_admin('admin@warrn.com', 'admin123')