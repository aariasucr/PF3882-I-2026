import configcatclient
import time
import logging

# Set the log level to INFO to track how your feature flags were evaluated. When moving to production, you can remove this line to avoid too detailed logging.
logging.basicConfig(level=logging.INFO)

configcat_client = configcatclient.get(
    # <-- This is the actual SDK Key for your Test Environment environment.
    'configcat-sdk-1/Qa3dCJKDvEuFMc04-qIUiQ/ty9sv_zipE2nnozLV8By7g'
)

patito = configcat_client.get_value('patito', False)

# print('patito\'s value from ConfigCat: ' + str(patito))

while True:
    patito = configcat_client.get_value('patito', False)
    emoji = '✅' if patito else '❌'
    print('Valor de patito en ConfigCat: ' + str(patito) + ' ' + emoji)
    time.sleep(5)
