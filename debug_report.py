
from app import app, db, Report
import uuid
import os

with app.app_context():
    try:
        print("Attempting to create a test report...")
        unique_id = uuid.uuid4().hex
        filename = f"debug_{unique_id}.jpg"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Create a dummy file
        with open(image_path, 'wb') as f:
            f.write(b'test')
            
        new_report = Report(
            latitude=15.4404,
            longitude=75.0145,
            animal_type='DebugAnimal',
            condition='Critical',
            description="Debug System Test Report",
            image_filename=filename,
            ai_species_suggestion='Debug',
            accident_severity='critical',
            status='New'
        )
        
        db.session.add(new_report)
        db.session.commit()
        print(f"SUCCESS: Created report ID {new_report.id}")
        
    except Exception as e:
        print(f"FAILURE: {e}")
        import traceback
        traceback.print_exc()
