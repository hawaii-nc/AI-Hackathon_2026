from google import genai
from app.core.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

def generate_referral(client_profile: dict, shelter: dict) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""You are a professional social worker assistant generating referral letters.
Write clearly, professionally, and with zero bias.
Do not include race, ethnicity, religion, or any protected characteristics.
Focus only on service needs and resource fit.

Client needs: {client_profile.get("needs")}
Urgency: {client_profile.get("urgency")}
Has children: {client_profile.get("has_children")}
Veteran: {client_profile.get("veteran")}

Referring to:
Organization: {shelter.get("name")}
Address: {shelter.get("address")}, {shelter.get("city")}
Phone: {shelter.get("phone")}
Type: {shelter.get("type")}

Write a professional referral letter."""
    )
    return response.text