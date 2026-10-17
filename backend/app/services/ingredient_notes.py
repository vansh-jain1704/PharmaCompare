"""
General patient-information notes for common active ingredients, used by the
no-API-key "Explain this medicine" fallback.

WHAT THIS IS, AND IS NOT
  The Medicines table holds names, salts, strengths, forms and prices - it
  holds nothing about what a medicine treats, its usual dose, precautions or
  side effects. Those four lines therefore cannot be "built from the DB"; they
  are hand-written reference text of the kind printed in a patient leaflet,
  keyed by active ingredient. Each entry is deliberately conservative
  (usual adult figures, widely documented effects, no rare warnings) and is
  shown with a disclaimer that the prescription, not this text, decides the
  dose. An ingredient that is not listed here gets NO invented notes - the
  explainer says the detail is unavailable instead.

  Adding an ingredient: key is the lower-case salt as it appears in
  Medicines.primary_salt / secondary_salt (see ALIASES for spellings).
  Keep each field to one or two short sentences, in plain language.
"""

ALIASES = {
    "acetaminophen": "paracetamol",
    "amoxicillin": "amoxycillin",
    "mecobalamin": "methylcobalamin",
    "acetylsalicylic acid": "aspirin",
}

NOTES = {
    "paracetamol": {
        "uses": "Relieves mild to moderate pain and brings down fever.",
        "dose": "Usually 500 mg to 1 g every 4 to 6 hours as needed, and no more than 4 g in 24 hours.",
        "precautions": "Do not take other medicines that also contain paracetamol at the same time. Take extra care with liver disease or regular alcohol use.",
        "side_effects": "Rarely causes problems at normal doses; an allergic rash is uncommon. Too much can seriously damage the liver.",
    },
    "ibuprofen": {
        "uses": "Relieves pain, reduces inflammation and lowers fever.",
        "dose": "Usually 200 to 400 mg every 6 to 8 hours with food, for the shortest time needed.",
        "precautions": "Take it with food. Tell your doctor if you have stomach ulcers, kidney problems, asthma or heart disease.",
        "side_effects": "Stomach upset, heartburn and nausea are common. It can irritate the stomach lining with longer use.",
    },
    "aceclofenac": {
        "uses": "Relieves pain and swelling, for example from joint, muscle or dental pain.",
        "dose": "Usually 100 mg twice a day after food.",
        "precautions": "Take it after food. Tell your doctor about stomach ulcers, kidney, liver or heart problems, or asthma.",
        "side_effects": "Stomach upset, indigestion and nausea are common. Dizziness can occur.",
    },
    "diclofenac": {
        "uses": "Relieves pain and inflammation, for example in joint or muscle pain.",
        "dose": "Usually 50 mg two or three times a day after food.",
        "precautions": "Take it after food. Tell your doctor about stomach ulcers, kidney, liver or heart problems, or asthma.",
        "side_effects": "Stomach pain, indigestion and nausea are common. Headache and dizziness can occur.",
    },
    "nimesulide": {
        "uses": "Relieves pain and fever.",
        "dose": "Usually 100 mg twice a day after food, for a short course only.",
        "precautions": "Not for long-term use because it can affect the liver. Avoid alcohol, and tell your doctor about any liver or stomach problems.",
        "side_effects": "Stomach upset and nausea are common. Stop and see a doctor if you notice yellow skin or eyes, or dark urine.",
    },
    "etoricoxib": {
        "uses": "Relieves pain and swelling in conditions such as arthritis.",
        "dose": "Usually 60 to 120 mg once a day, depending on the condition.",
        "precautions": "Tell your doctor if you have high blood pressure, heart, kidney or liver problems, or stomach ulcers.",
        "side_effects": "Stomach upset, headache and swelling of the feet can occur. It can raise blood pressure.",
    },
    "amoxycillin": {
        "uses": "An antibiotic used for bacterial infections such as throat, ear, chest and urinary infections.",
        "dose": "Commonly 250 to 500 mg three times a day, for the full number of days prescribed.",
        "precautions": "Tell your doctor if you are allergic to penicillin. Finish the course even if you feel better.",
        "side_effects": "Loose stools, nausea and a mild rash are common. A swollen face or trouble breathing needs urgent medical help.",
    },
    "azithromycin": {
        "uses": "An antibiotic used for bacterial infections of the chest, throat, ear and skin.",
        "dose": "Commonly 500 mg once a day for 3 days, or as your doctor prescribes.",
        "precautions": "Tell your doctor about heart rhythm problems or liver disease. Finish the course even if you feel better.",
        "side_effects": "Loose stools, stomach pain and nausea are common.",
    },
    "cefixime": {
        "uses": "An antibiotic used for bacterial infections such as throat, chest, ear and urinary infections.",
        "dose": "Commonly 200 mg twice a day or 400 mg once a day, for the days prescribed.",
        "precautions": "Tell your doctor if you are allergic to penicillin or cephalosporin antibiotics. Finish the course.",
        "side_effects": "Loose stools, stomach pain and nausea are common.",
    },
    "ofloxacin": {
        "uses": "An antibiotic used for infections such as urinary, chest and stomach infections.",
        "dose": "Commonly 200 to 400 mg twice a day, for the days prescribed.",
        "precautions": "Avoid taking it at the same time as antacids or iron. Stop and call your doctor if you get tendon pain.",
        "side_effects": "Nausea, loose stools, headache and dizziness can occur.",
    },
    "ciprofloxacin": {
        "uses": "An antibiotic used for infections such as urinary, stomach and chest infections.",
        "dose": "Commonly 250 to 750 mg twice a day, for the days prescribed.",
        "precautions": "Avoid taking it at the same time as antacids, iron or calcium. Stop and call your doctor if you get tendon pain.",
        "side_effects": "Nausea, loose stools, headache and dizziness can occur.",
    },
    "levofloxacin": {
        "uses": "An antibiotic used for infections such as chest, sinus, urinary and skin infections.",
        "dose": "Commonly 250 to 750 mg once a day, for the days prescribed.",
        "precautions": "Avoid taking it at the same time as antacids, iron or calcium. Stop and call your doctor if you get tendon pain.",
        "side_effects": "Nausea, loose stools, headache and dizziness can occur.",
    },
    "domperidone": {
        "uses": "Relieves nausea, vomiting and a feeling of fullness after meals.",
        "dose": "Usually 10 mg up to three times a day, before meals.",
        "precautions": "Use for the shortest time needed. Tell your doctor about heart rhythm problems or liver disease.",
        "side_effects": "Dry mouth and headache can occur. Rarely it affects the heart rhythm.",
    },
    "ondansetron": {
        "uses": "Prevents and relieves nausea and vomiting.",
        "dose": "Usually 4 to 8 mg, up to three times a day.",
        "precautions": "Tell your doctor about heart rhythm problems or if you take other medicines that affect the heart.",
        "side_effects": "Headache, constipation and tiredness are common.",
    },
    "pantoprazole": {
        "uses": "Reduces stomach acid, for acidity, heartburn, reflux and stomach ulcers.",
        "dose": "Usually 40 mg once a day, before breakfast.",
        "precautions": "Take it on an empty stomach, about 30 minutes before food. Long-term use should be reviewed by your doctor.",
        "side_effects": "Headache, loose stools or constipation and stomach discomfort can occur.",
    },
    "omeprazole": {
        "uses": "Reduces stomach acid, for acidity, heartburn, reflux and stomach ulcers.",
        "dose": "Usually 20 mg once a day, before food.",
        "precautions": "Take it on an empty stomach, before a meal. Long-term use should be reviewed by your doctor.",
        "side_effects": "Headache, loose stools or constipation and stomach discomfort can occur.",
    },
    "rabeprazole": {
        "uses": "Reduces stomach acid, for acidity, heartburn, reflux and stomach ulcers.",
        "dose": "Usually 20 mg once a day, before food.",
        "precautions": "Take it before a meal. Long-term use should be reviewed by your doctor.",
        "side_effects": "Headache, loose stools or constipation and stomach discomfort can occur.",
    },
    "cetirizine": {
        "uses": "Relieves allergy symptoms such as sneezing, runny nose, itchy eyes and hives.",
        "dose": "Usually 10 mg once a day.",
        "precautions": "It can cause drowsiness, so take care when driving. Avoid alcohol.",
        "side_effects": "Drowsiness, dry mouth and tiredness are common.",
    },
    "levocetirizine": {
        "uses": "Relieves allergy symptoms such as sneezing, runny nose, itchy eyes and hives.",
        "dose": "Usually 5 mg once a day, often in the evening.",
        "precautions": "It can cause drowsiness, so take care when driving. Avoid alcohol.",
        "side_effects": "Drowsiness, dry mouth and tiredness are common.",
    },
    "chlorpheniramine maleate": {
        "uses": "Relieves allergy and cold symptoms such as sneezing, runny nose and itching.",
        "dose": "Usually 4 mg every 4 to 6 hours, and no more than 24 mg a day.",
        "precautions": "It commonly causes sleepiness, so avoid driving and alcohol.",
        "side_effects": "Drowsiness, dry mouth and blurred vision are common.",
    },
    "metformin": {
        "uses": "Lowers blood sugar in type 2 diabetes.",
        "dose": "Usually started at 500 mg once or twice a day with meals and adjusted by the doctor.",
        "precautions": "Take it with food. Tell your doctor about kidney problems, and before any scan that uses contrast dye.",
        "side_effects": "Nausea, loose stools and stomach upset are common, mostly early on.",
    },
    "glimepiride": {
        "uses": "Lowers blood sugar in type 2 diabetes.",
        "dose": "Usually 1 to 4 mg once a day with breakfast.",
        "precautions": "Do not skip meals - it can make blood sugar too low. Know the signs: sweating, shaking, hunger, confusion.",
        "side_effects": "Low blood sugar is the main risk. Weight gain and nausea can occur.",
    },
    "telmisartan": {
        "uses": "Lowers high blood pressure and protects the heart and kidneys.",
        "dose": "Usually 40 mg once a day.",
        "precautions": "Not for use in pregnancy. Tell your doctor about kidney problems or if you take potassium supplements.",
        "side_effects": "Dizziness and tiredness can occur, especially when you stand up quickly.",
    },
    "amlodipine": {
        "uses": "Lowers high blood pressure and helps prevent chest pain (angina).",
        "dose": "Usually 5 mg once a day.",
        "precautions": "Take it at the same time each day. Do not stop suddenly without asking your doctor.",
        "side_effects": "Swollen ankles, flushing, headache and tiredness are common.",
    },
    "atorvastatin": {
        "uses": "Lowers cholesterol and reduces the risk of heart attack and stroke.",
        "dose": "Usually 10 to 40 mg once a day.",
        "precautions": "Tell your doctor about liver disease or pregnancy. Report unexplained muscle pain.",
        "side_effects": "Muscle aches, headache and mild stomach upset can occur.",
    },
    "rosuvastatin": {
        "uses": "Lowers cholesterol and reduces the risk of heart attack and stroke.",
        "dose": "Usually 5 to 20 mg once a day.",
        "precautions": "Tell your doctor about liver or kidney disease or pregnancy. Report unexplained muscle pain.",
        "side_effects": "Muscle aches, headache and mild stomach upset can occur.",
    },
    "loperamide": {
        "uses": "Slows down sudden loose motions (diarrhoea).",
        "dose": "Usually 4 mg at first, then 2 mg after each loose stool, to a daily limit set on the pack or by your doctor.",
        "precautions": "Drink plenty of fluids. Do not use it if there is blood in the stool or a high fever, and do not give it to young children.",
        "side_effects": "Constipation, stomach cramps and bloating can occur.",
    },
    "ambroxol": {
        "uses": "Thins and loosens mucus so a chesty cough is easier to clear.",
        "dose": "Usually 30 mg two or three times a day.",
        "precautions": "Drink plenty of fluids. Tell your doctor if the cough lasts more than a week.",
        "side_effects": "Mild stomach upset or nausea can occur.",
    },
    "methylcobalamin": {
        "uses": "A form of vitamin B12, used for B12 deficiency and nerve-related tingling or numbness.",
        "dose": "Commonly 500 to 1500 mcg a day.",
        "precautions": "Tell your doctor if you are pregnant or have a vitamin B12 absorption problem.",
        "side_effects": "Usually well tolerated; mild nausea or loose stools are uncommon.",
    },
    "fluconazole": {
        "uses": "An antifungal used for yeast and fungal infections such as thrush.",
        "dose": "Often a single 150 mg dose for thrush; other infections need daily doses set by the doctor.",
        "precautions": "Tell your doctor about liver problems or heart rhythm problems, and about all your other medicines.",
        "side_effects": "Nausea, headache and stomach pain can occur.",
    },
    "aspirin": {
        "uses": "In low doses, helps prevent blood clots; in higher doses it relieves pain and fever.",
        "dose": "Usually 75 mg once a day for heart protection; higher doses for pain are set by the doctor.",
        "precautions": "Take it with food. Tell your doctor about stomach ulcers, bleeding problems or asthma. Not for children with fever.",
        "side_effects": "Stomach irritation and easier bruising or bleeding can occur.",
    },
    "montelukast": {
        "uses": "Helps prevent asthma attacks and relieves allergic rhinitis.",
        "dose": "Usually 10 mg once a day in the evening.",
        "precautions": "It does not treat a sudden asthma attack. Tell your doctor about any mood changes or sleep problems.",
        "side_effects": "Headache and stomach upset can occur.",
    },
}


def lookup(salt):
    """Returns the notes for an ingredient, or None when we have none."""
    if not salt:
        return None
    key = salt.strip().lower()
    return NOTES.get(ALIASES.get(key, key))
