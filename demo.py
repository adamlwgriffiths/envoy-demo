# demonstrates background encoding/decoding of messages
# using python 3's asyncio
import asyncio
import json
from async_timeout import timeout as asyncio_timeout

# TODO: add a method that monitors for specific values
# the following must all be true at the SAME TIME
#     wait_values_at_once(
#           ('/a/1', '==', 1),
#           ('/b/3', '==', 3))
# the following must all be true at one time
#     wait_values(
#           ('/a/1', '==', 1),
#           ('/b/3', '==', 3))

# state structure contains current message payloads
# *_event values hold async conditions
# functions can wait on the condition, and they will be
# woken up when the message arrives
state = {
    'a_event': None,
    'a': {'1': 0, '2': 0},
    'b_event': None,
    'b': {'3': 0, '4': 0},
    'c_event': None,
    'c': {'5': 0, '6': 0},
}

def create_conditions():
    # must be called from within asyncio event loop context
    state['a_event'] = asyncio.Condition()
    state['b_event'] = asyncio.Condition()
    state['c_event'] = asyncio.Condition()


async def protocol_x_decoder(message):
    async def decode_a(data):
        state['a'] = data
        cond = state['a_event']
        async with cond:
            cond.notify_all()
    async def decode_b(data):
        state['b'] = data
        cond = state['b_event']
        async with cond:
            cond.notify_all()
    async def decode_c(data):
        state['c'] = data
        cond = state['c_event']
        async with cond:
            cond.notify_all()

    decoders = {
        'a': decode_a,
        'b': decode_b,
        'c': decode_c,
    }

    data = json.loads(message)
    type_ = data['type']
    payload = data['payload']

    decoder = decoders.get(type_)
    if not decoder:
        raise ValueError(f'Unknown message type {repr(type_)}')
    await decoder(payload)

class UDP_Decoder:
    # using python asyncio transport
    # https://docs.python.org/3/library/asyncio-protocol.html#udp-echo-server
    def __init__(self, decoder):
        self.decoder = decoder
        self.loop = asyncio.get_running_loop()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        message = data.decode()
        #self.loop.call_soon(self.decoder, message)
        self.loop.create_task(self.decoder(message))

    def connection_lost(self, exc):
        print('Decoder connection closed')

class UDP_Generator:
    # https://docs.python.org/3/library/asyncio-protocol.html#udp-echo-client
    # generates random 'X protocol' messages
    def __init__(self, on_con_lost):
        self.on_con_lost = on_con_lost
        self.transport = None
        self.loop = asyncio.get_running_loop()

        # store some local state we use to generate messages with
        self.data = {
            'a': {'type': 'a', 'payload': {'1': 1, '2': 1}},
            'b': {'type': 'b', 'payload': {'3': 1, '4': 1}},
            'c': {'type': 'c', 'payload': {'5': 1, '6': 1}},
        }
        self.frequencies = {
            'a': 10.0,
            'b': 5.0,
            'c': 1.0,
        }

    def connection_made(self, transport):
        self.transport = transport

        # make some tasks which encode various messages
        # and run at different rates
        self.loop.create_task(self.send_x_message('a'))
        self.loop.create_task(self.send_x_message('b'))
        self.loop.create_task(self.send_x_message('c'))

    async def send_x_message(self, type_):
        assert self.transport
        state = self.data[type_]

        while True:
            # encode our message into json and send it
            data = json.dumps(state)
            self.transport.sendto(data.encode())

            # increment our values
            for k, v in state['payload'].items():
                state['payload'][k] = v + v

            # sleep until its time to send again
            await asyncio.sleep(1.0 / self.frequencies[type_])

    def error_received(self, exc):
        print('Error received:', exc)

    def connection_lost(self, exc):
        print('Encoder connection closed')
        self.on_con_lost.set_result(True)


async def await_message(message):
    # wait for the arrival of the specified message
    # returns the message name
    cond = state[f'{message}_event']
    async with cond:
        await cond.wait()
    return message

async def await_all_messages(*messages):
    # awaits the return of all of the provided messages
    # note: repeated calls to this may cause undesirable behaviour
    # as this will only return when ALL messages have arrived
    # any messages with different frequencies may cause the follow-on
    # code to miss intermediate values
    tasks = [await_message(x) for x in messages]
    await asyncio.gather(*tasks)
    return messages

async def await_any_messages(*messages):
    # awaits the return of 1 of the provided messages
    # awaiting _both_ may cause our follow-on condition to be missed
    # if they are out of frequency
    tasks = [await_message(x) for x in messages]
    completed, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    completed_messages = [task.result() for task in completed]
    return completed_messages

async def message_arrival_notifier():
    '''Helper task that prints when a message of type "X" arrives'''
    while True:
        arrived = await await_any_messages('a', 'b', 'c')
        print(f'Message {", ".join(arrived)} arrived')


async def message_monitor():
    '''example of a function that waits for various message conditions to trigger'''
    # run for at most, N seconds
    try:
        async with asyncio_timeout(2):
            while True:
                arrived = await await_any_messages('a', 'b')
                print(f'{", ".join(arrived)} arrived')

                # determined by viewing the printouts
                if (
                    state['a']['1'] == 512 and
                    state['b']['3'] == 16
                ):
                    break

                print(f'a:1 = {state["a"]["1"]}, b:3 = {state["b"]["3"]}')

            print('****** CONDITION MET')
    except asyncio.TimeoutError:
        print('****** CONDITIONS FAILED!')


async def main_logic():
    '''main application logic pulled out into a function to separate from boilerplate'''
    for x in range(10):
        await asyncio.sleep(1)
        clean_state = {k:v for k,v in state.items() if k in ['a', 'b', 'c']}
        print(clean_state)


async def main():
    '''main function that sets up tasks and starts the application logic'''
    loop = asyncio.get_running_loop()

    # conditions, events, etc must be made within the loop
    create_conditions()

    recv_transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDP_Decoder(protocol_x_decoder),
        local_addr=('127.0.0.1', 9999)
    )

    on_con_lost = loop.create_future()
    send_transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDP_Generator(on_con_lost),
        remote_addr=('127.0.0.1', 9999)
    )

    loop.create_task(message_arrival_notifier())
    loop.create_task(message_monitor())

    try:
        await main_logic()
    finally:
        send_transport.close()
        recv_transport.close()

asyncio.run(main())

