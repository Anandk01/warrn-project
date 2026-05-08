import re
from services.rag_service import rag_service
from services.gemini_service import gemini_service

class ChatbotService:
    def __init__(self, db_session, report_model):
        self.db = db_session
        self.Report = report_model

    def process_query(self, user_query):
        """Processes query with strict priority routing."""
        
        # 1. Check for Case Status Priority (Regex first for speed)
        case_id_match = re.search(r'#?(\d+)', user_query)
        # If user explicitly mentions "status", "case", "report" OR just gives an ID in a short query
        if any(word in user_query.lower() for word in ["status", "case", "report", "update"]) or (case_id_match and len(user_query) < 10):
             # Let's use Gemini to confirm if it IS a status query or something else
             intent = gemini_service.classify_intent(user_query)
             if intent == "status_query":
                 return self._handle_status_query(user_query, case_id_match)

        # 2. Use Gemini for general intent classification if not already decided
        intent = gemini_service.classify_intent(user_query)
        
        # Priority Order: status_query > emergency > rag > general
        if intent == "status_query":
            return self._handle_status_query(user_query, case_id_match)
        
        if intent == "emergency":
            return self._handle_emergency(user_query)
            
        if intent == "rag":
            # Check if RAG actually finds something
            context_chunks = rag_service.search(user_query)
            if context_chunks:
                return self._handle_rag(user_query, context_chunks)
            else:
                # If RAG fails to find info, fallback to Gemini general
                return self._handle_general(user_query)
        
        # Final Fallback
        return self._handle_general(user_query)

    def _handle_status_query(self, query, match):
        if match:
            case_id = int(match.group(1))
            report = self.Report.query.get(case_id)
            if report:
                data = {
                    "id": report.id,
                    "animal": report.animal_type,
                    "status": report.status,
                    "location": f"{report.city or 'Unknown'}",
                    "severity": report.accident_severity,
                    "notes": report.description
                }
                reply = gemini_service.generate_response(query, context=str(data), is_status=True)
                return reply, "status_query", case_id
            else:
                return f"I couldn't find a report with ID #{case_id}. Please verify the number.", "status_query", case_id
        
        return "I can check your case status! Please provide the Report ID (e.g., #112).", "status_query", None

    def _handle_emergency(self, query):
        reply = gemini_service.generate_response(query)
        warning = "\n\n🚨 **EMERGENCY NOTICE:** If this is a life-threatening situation, please contact a vet or local rescue immediately. You can also file a formal report on our home page."
        return reply + warning, "emergency", None

    def _handle_rag(self, query, chunks):
        context = "\n---\n".join(chunks)
        reply = gemini_service.generate_response(query, context=context)
        return reply, "rag", None

    def _handle_general(self, query):
        reply = gemini_service.generate_response(query)
        return reply, "general", None
