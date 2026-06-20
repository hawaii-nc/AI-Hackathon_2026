from openai import OpenAI
from app.core.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_referral(client_profile: dict, shelter: dict) -> str:
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {
                'role': 'system',
                'content': '''You are a professional social worker assistant generating referral letters.
                Write clearly, professionally, and with zero bias.
                Do not include race, ethnicity, religion, or any protected characteristics.
                Focus only on service needs and resource fit.'''
            },
            {
                'role': 'user',
                'content': f'''Generate a referral letter for:
                Client needs: {client_profile.get("needs")}
                Urgency: {client_profile.get("urgency")}
                Has children: {client_profile.get("has_children")}
                Veteran: {client_profile.get("veteran")}
                
                Referring to:
                Organization: {shelter.get("name")}
                Address: {shelter.get("address")}, {shelter.get("city")}
                Phone: {shelter.get("phone")}
                Type: {shelter.get("type")}'''
            }
        ]
    )
    return response.choices[0].message.content
