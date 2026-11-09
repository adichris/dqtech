"""Ghana delivery catalogue. Town suggestions are not an exhaustive gazetteer.

Region/capital reference: https://lgs.gov.gh/regions/
Customers may enter any town within a region; no external lookup is needed.
"""
REGIONS = {
    'Ahafo': ['Goaso', 'Bechem', 'Duayaw Nkwanta', 'Kenyasi', 'Hwidiem'],
    'Ashanti': ['Kumasi', 'Obuasi', 'Ejisu', 'Mampong', 'Konongo', 'Offinso', 'Bekwai', 'Agogo', 'Juaben'],
    'Bono': ['Sunyani', 'Berekum', 'Dormaa Ahenkro', 'Wenchi', 'Sampa', 'Banda Ahenkro'],
    'Bono East': ['Techiman', 'Kintampo', 'Nkoranza', 'Atebubu', 'Yeji', 'Prang'],
    'Central': ['Cape Coast', 'Winneba', 'Kasoa', 'Elmina', 'Mankessim', 'Swedru', 'Dunkwa-on-Offin', 'Assin Fosu'],
    'Eastern': ['Koforidua', 'Nkawkaw', 'Akim Oda', 'Nsawam', 'Akropong', 'Aburi', 'Somanya', 'Kibi', 'Asamankese'],
    'Greater Accra': ['Accra', 'Tema', 'Madina', 'Adenta', 'Ashaiman', 'Teshie', 'Nungua', 'Dodowa', 'Amasaman', 'Ada Foah', 'Prampram'],
    'North East': ['Nalerigu', 'Gambaga', 'Walewale', 'Bunkpurugu', 'Chereponi', 'Yagaba'],
    'Northern': ['Tamale', 'Yendi', 'Savelugu', 'Tolon', 'Bimbilla', 'Kumbungu', 'Karaga'],
    'Oti': ['Dambai', 'Nkwanta', 'Jasikan', 'Kadjebi', 'Kete Krachi', 'Kpassa'],
    'Savannah': ['Damongo', 'Bole', 'Salaga', 'Buipe', 'Daboya', 'Sawla'],
    'Upper East': ['Bolgatanga', 'Navrongo', 'Bawku', 'Paga', 'Zebilla', 'Bongo', 'Sandema'],
    'Upper West': ['Wa', 'Lawra', 'Tumu', 'Jirapa', 'Nandom', 'Nadowli', 'Gwollu'],
    'Volta': ['Ho', 'Hohoe', 'Keta', 'Aflao', 'Sogakope', 'Kpando', 'Anloga', 'Akatsi', 'Dzodze'],
    'Western': ['Sekondi-Takoradi', 'Sekondi', 'Takoradi', 'Tarkwa', 'Axim', 'Agona Nkwanta', 'Shama', 'Prestea', 'Elubo'],
    'Western North': ['Sefwi Wiawso', 'Bibiani', 'Sefwi Bekwai', 'Juaboso', 'Enchi', 'Dadieso', 'Bodi'],
}
