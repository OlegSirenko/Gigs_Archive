# bot/moderator_states.py
"""
FSM states for moderator description editing flow.
"""

from aiogram.fsm.state import State, StatesGroup

class ModeratorEdit(StatesGroup):
    """States for moderator final description workflow"""
    waiting_for_description = State()  # Moderator typing the final caption
    waiting_for_confirmation = State()  # Moderator reviewing preview