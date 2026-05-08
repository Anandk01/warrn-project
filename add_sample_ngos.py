from app import app, db, NGO

def add_sample_ngos():
    with app.app_context():
        sample_ngos = [
            {
                'name': 'Wildlife SOS Delhi',
                'email': 'delhi@wildlifesos.org',
                'phone': '+91-11-4653-8300',
                'latitude': 28.6139,
                'longitude': 77.2090,
                'specialization': 'Wildlife Rescue',
                'coverage_radius': 15.0
            },
            {
                'name': 'Animal Aid Unlimited',
                'email': 'info@animalaidunlimited.org',
                'phone': '+91-294-251-0333',
                'latitude': 24.5854,
                'longitude': 73.7125,
                'specialization': 'Street Animals',
                'coverage_radius': 20.0
            },
            {
                'name': 'Blue Cross of India',
                'email': 'contact@bluecrossofindia.org',
                'phone': '+91-44-2234-1404',
                'latitude': 13.0827,
                'longitude': 80.2707,
                'specialization': 'Animal Welfare',
                'coverage_radius': 25.0
            }
        ]
        
        for ngo_data in sample_ngos:
            existing = NGO.query.filter_by(email=ngo_data['email']).first()
            if not existing:
                ngo = NGO(**ngo_data)
                db.session.add(ngo)
        
        db.session.commit()
        print("Sample NGOs added successfully!")

if __name__ == '__main__':
    add_sample_ngos()