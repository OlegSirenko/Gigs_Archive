from aiogram.fsm.state import State, StatesGroup

class PosterSubmission(StatesGroup):
    """FSM states for poster submission flow"""
    waiting_for_photo = State()
    waiting_for_anonymous = State()
    waiting_for_date = State()
    waiting_for_confirmation = State()