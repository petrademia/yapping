import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from trace_albaz_combo import (
    new_duel, FALLEN_WHITE, ALBION_BRANDED, INCREDIBLE_ECCLESIA,
    ECCLESIA_DARK_DRAGON, GUIDING_QUEM, TRIBRIGADE_SPRINGANS_KITT,
    THREE_CHAMPIONS, BLAZING_CARTESIA, GRANGUIGNOL, DEVOURS_DOGMA,
    CELTIC_GUARDIAN, DROLL_LOCK_BIRD,
)

def step(duel, decision, kind, card=None):
    for i, action in enumerate(decision['actions']):
        if action['kind'] == kind and (card is None or action['card'] == card):
            return duel.step(i)
    raise RuntimeError(f'missing {kind} {card}: {decision["actions"]}')

def settle(duel, decision):
    while True:
        kinds={a['kind'] for a in decision['actions']}
        kind=next((k for k in ('place','position','pass') if k in kinds),None)
        if kind is None: return decision
        decision=step(duel,decision,kind)

def settle_forced(duel, decision):
    while True:
        kinds = {a['kind'] for a in decision['actions']}
        kind = next((k for k in ('place', 'position') if k in kinds), None)
        if kind is None:
            return decision
        decision = step(duel, decision, kind)

def main():
    hand=[FALLEN_WHITE,CELTIC_GUARDIAN,CELTIC_GUARDIAN,CELTIC_GUARDIAN,CELTIC_GUARDIAN]
    extra=[41373230,78397661,74405783,87746184,44146295,76666602,24915933,72578374]
    interruption = os.getenv("YAPPING_MDM_INTERRUPTION")
    opponent_card = DROLL_LOCK_BIRD if interruption == "droll" else None
    duel, decision=new_duel(opponent_card=opponent_card, opening_hand=hand, extra_deck=extra)
    decision=step(duel,decision,'summon',FALLEN_WHITE)
    decision=settle(duel,decision)
    decision=step(duel,decision,'yes',FALLEN_WHITE)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',INCREDIBLE_ECCLESIA)
    decision=settle(duel,decision)
    decision=step(duel,decision,'special_summon',ECCLESIA_DARK_DRAGON)
    decision=step(duel,decision,'select_card',INCREDIBLE_ECCLESIA)
    decision=step(duel,decision,'select_sum',FALLEN_WHITE)
    decision=settle(duel,decision)
    decision=step(duel,decision,'activate',ECCLESIA_DARK_DRAGON)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',GUIDING_QUEM)
    decision=settle(duel,decision)
    decision=step(duel,decision,'yes',GUIDING_QUEM)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',TRIBRIGADE_SPRINGANS_KITT)
    decision=settle(duel,decision)
    decision=step(duel,decision,'yes',TRIBRIGADE_SPRINGANS_KITT)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',FALLEN_WHITE)
    decision=settle(duel,decision)
    decision=step(duel,decision,'special_summon',THREE_CHAMPIONS)
    decision=step(duel,decision,'select_card',GUIDING_QUEM)
    decision=step(duel,decision,'select_sum',FALLEN_WHITE)
    decision=settle(duel,decision)
    decision=step(duel,decision,'yes',THREE_CHAMPIONS)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',BLAZING_CARTESIA)
    print('AFTER CARTESIA SEARCH', decision['actions'])
    decision=step(duel,decision,'pass')
    decision=step(duel,decision,'pass')
    decision=step(duel,decision,'activate',BLAZING_CARTESIA)
    decision=settle(duel,decision)
    decision=step(duel,decision,'activate',BLAZING_CARTESIA)
    decision=settle(duel,decision)
    decision=step(duel,decision,'select_card',GRANGUIGNOL)
    decision=step(duel,decision,'select_toggle',THREE_CHAMPIONS)
    decision=step(duel,decision,'select_toggle',BLAZING_CARTESIA)
    decision=settle(duel,decision)
    decision=step(duel,decision,'yes',GRANGUIGNOL)
    decision=settle(duel,decision)
    print('AFTER GRANGUIGNOL', decision['actions'])
    decision=step(duel,decision,'select_card',DEVOURS_DOGMA)
    decision=settle(duel,decision)
    print('AFTER DEVOURS SEND', decision['actions'])
    decision=step(duel,decision,'end_phase')
    print('END PHASE 1', decision['actions'])
    decision=step(duel,decision,'pass')
    print('END PHASE 2', decision['actions'])
    decision=step(duel,decision,'chain',DEVOURS_DOGMA)
    print('DEVOURS CHAIN', decision['actions'])
    decision=step(duel,decision,'pass')
    print('DEVOURS RESOLVE', decision['actions'])
    decision=step(duel,decision,'pass')
    print('AFTER DEVOURS RESOLVE 2', decision['actions'])
    decision=step(duel,decision,'select_card',30271097)
    decision=settle(duel,decision)
    print('FALLEN VIRTUOUS ADDED', decision['actions'])
    decision=step(duel,decision,'chain',BLAZING_CARTESIA)
    decision=settle_forced(duel,decision)
    print('CARTESIA RETURN VALIDATED', decision['actions'])
    decision=step(duel,decision,'pass')
    decision=step(duel,decision,'pass')
    decision=step(duel,decision,'pass')
    print('AFTER FALLEN VIRTUOUS SECOND PASS', decision['actions'])
    print('MDM ONE CARD PARTIAL VALIDATED')
    return

if __name__ == '__main__': main()
