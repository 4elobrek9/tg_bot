class Actions:
    RP_ACTIONS = [
        "ударить", "поцеловать", "обнять", "укусить",
        "погладить", "толкнуть", "ущипнуть", "шлепнуть", "пощечина",
        "пнуть", "схватить", "заплакать", "засмеяться",
        "удивиться", "разозлиться", "испугаться", "подмигнуть", "шепнуть",
        "издеваться"
    ]

    INTIMATE_ACTIONS = {
        "добрые": {
            "поцеловать": {"hp_change_target": +10, "hp_change_sender": -5},
            "обнять": {"hp_change_target": +15, "hp_change_sender": +15},
            "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
            "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"hp_change_target": +9, "hp_change_sender": -4},
            "напоить": {"hp_change_target": +6, "hp_change_sender": -3},
            "сделать массаж": {"hp_change_target": +15, "hp_change_sender": -4},
            "спеть песню": {"hp_change_target": +5, "hp_change_sender": -1},
            "подарить цветы": {"hp_change_target": +12, "hp_change_sender": -6},
            "подрочить": {"hp_change_target": +12, "hp_change_sender": +6},
        },
        "нейтральные": {
            "толкнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "схватить": {"hp_change_target": 0, "hp_change_sender": 0},
            "помахать": {"hp_change_target": 0, "hp_change_sender": 0},
            "кивнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "похлопать": {"hp_change_target": 0, "hp_change_sender": 0},
            "постучать": {"hp_change_target": 0, "hp_change_sender": 0},
            "попрощаться": {"hp_change_target": 0, "hp_change_sender": 0},
            "шепнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "почесать спинку": {"hp_change_target": +5, "hp_change_sender": 0},
        },
        "злые": {
            "уебать": {"hp_change_target": -20, "hp_change_sender": 0},
            "схватить за шею": {"hp_change_target": -25, "hp_change_sender": 0},
            "ударить": {"hp_change_target": -10, "hp_change_sender": 0},
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": 0},
            "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": 0},
            "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"hp_change_target": -80, "hp_change_sender": 0},
        }
    }

    # Полный список всех действий
    ALL_ACTIONS = {
        "Добрые действия": list(INTIMATE_ACTIONS["добрые"].keys()),
        "Нейтральные действия": list(INTIMATE_ACTIONS["нейтральные"].keys()),  # Убедитесь, что здесь нет лишнего пробела
        "Злые действия": list(INTIMATE_ACTIONS["злые"].keys())
    }

    # Список всех команд для проверки
    ALL_COMMANDS = (
        set(INTIMATE_ACTIONS["добрые"].keys()) |
        set(INTIMATE_ACTIONS["нейтральные"].keys()) |  # Убедитесь, что здесь нет лишнего пробела
        set(INTIMATE_ACTIONS["злые"].keys())
    )
