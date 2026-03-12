import sqlite3
import glob
import os

_contact_cache = None

def get_mac_contacts() -> dict[str, str]:
    """Read all macOS contacts from the AddressBook SQLite databases."""
    global _contact_cache
    if _contact_cache is not None:
        return _contact_cache
        
    base_path = os.path.expanduser("~/Library/Application Support/AddressBook")
    db_paths = glob.glob(os.path.join(base_path, "**", "*.abcddb"), recursive=True)
    
    mapping = {}
    for db_path in db_paths:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # macOS Contacts schemas: ZABCDRECORD (ppl) and ZABCDPHONENUMBER
            query = """
                SELECT r.ZFIRSTNAME, r.ZLASTNAME, p.ZFULLNUMBER
                FROM ZABCDRECORD r
                JOIN ZABCDPHONENUMBER p ON r.Z_PK = p.ZOWNER
                WHERE p.ZFULLNUMBER IS NOT NULL
            """
            cursor.execute(query)
            for row in cursor.fetchall():
                first = row[0] or ""
                last = row[1] or ""
                phone = row[2]
                
                name_parts = [part for part in [first, last] if part]
                full_name = " ".join(name_parts).strip()
                
                if full_name and phone:
                    # Clean up phone number
                    norm_phone = "".join(c for c in phone if c.isdigit() or c == "+")
                    
                    if len(norm_phone) == 10 and not norm_phone.startswith("+"):
                        norm_phone = "+1" + norm_phone
                    elif len(norm_phone) == 11 and norm_phone.startswith("1"):
                        norm_phone = "+" + norm_phone
                    elif not norm_phone.startswith("+"):
                        norm_phone = "+" + norm_phone
                        
                    mapping[norm_phone] = full_name
            conn.close()
        except Exception:
            # Ignore DBs that cannot be parsed
            continue
            
    _contact_cache = mapping
    return mapping

def resolve_contact(identifier: str, default: str) -> str:
    """
    Resolve an identifier (phone number or ID containing one) to a Mac contact name.
    """
    if not identifier:
        return default
        
    contacts = get_mac_contacts()
    
    # Fast exact match
    if identifier in contacts:
        return contacts[identifier]
        
    # Extract phone-like digits and check if that matches
    # Beeper iMessage senderIDs sometimes look like `+12015550123:beeper.local`
    norm = "".join(c for c in identifier if c.isdigit() or c == "+")
    if norm in contacts:
        return contacts[norm]
        
    # Just checking if the string itself has a number we know
    for phone_num, name in contacts.items():
        if phone_num in identifier:
            return name
        
    return default
