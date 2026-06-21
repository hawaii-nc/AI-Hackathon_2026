from supabase import create_client
from app.core.config import SUPABASE_URL, SUPABASE_ANON_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_all_shelters():
    response = supabase.table('shelters').select('*').execute()
    return response.data

def get_shelters_by_island(island: str):
    response = supabase.table('shelters').select('*').eq('island', island).execute()
    return response.data

def save_client_profile(profile: dict):
    response = supabase.table('clients').insert(profile).execute()
    return response.data

def get_client_history(client_id: str):
    response = supabase.table('notes').select('*').eq('client_id', client_id).order('created_at', desc=True).execute()
    return response.data
