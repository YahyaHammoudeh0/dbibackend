#!/usr/bin/python3
import usb.core
import usb.util
import usb.backend.libusb1
import struct
import sys
import time
import argparse
import logging
import os
from enum import IntEnum
from collections import OrderedDict
from pathlib import Path


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.INFO)

BUFFER_SEGMENT_DATA_SIZE = 0x100000

SWITCH_VID = 0x057E
SWITCH_PID = 0x3000


class CommandID(IntEnum):
    EXIT = 0
    LIST_DEPRECATED = 1
    FILE_RANGE = 2
    LIST = 3


class CommandType(IntEnum):
    REQUEST = 0
    RESPONSE = 1
    ACK = 2


def _emit(on_event, kind, **kwargs):
    """Send a structured event to a listener (e.g. the GUI). No-op when unset."""
    if on_event is not None:
        payload = {'type': kind}
        payload.update(kwargs)
        on_event(payload)


def _is_timeout(err):
    """True when a USBError is just a read/write timeout (no data yet)."""
    if getattr(err, 'backend_error_code', None) == -7:  # LIBUSB_ERROR_TIMEOUT
        return True
    return 'timed out' in str(err).lower() or 'timeout' in str(err).lower()


def get_libusb_backend():
    """Locate a libusb backend.

    Checks, in order: a copy bundled next to the app (PyInstaller), common
    Homebrew locations, then pyusb's default resolver. This is what lets the
    packaged .app run without the user installing Homebrew or libusb.
    """
    import glob

    candidates = []
    # A copy bundled inside the packaged .app (named libusb-1.0.dylib or the
    # versioned libusb-1.0.0.dylib depending on the source).
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    candidates += sorted(glob.glob(os.path.join(bundle_dir, 'libusb-1.0*.dylib')))
    candidates += [
        '/opt/homebrew/lib/libusb-1.0.dylib',  # Apple Silicon Homebrew
        '/usr/local/lib/libusb-1.0.dylib',     # Intel Homebrew
    ]

    for path in candidates:
        if os.path.exists(path):
            backend = usb.backend.libusb1.get_backend(find_library=lambda x, p=path: p)
            if backend is not None:
                log.debug(f'Using libusb backend: {path}')
                return backend

    backend = usb.backend.libusb1.get_backend()
    if backend is None:
        raise RuntimeError(
            'Could not find libusb. Install it with "brew install libusb", '
            'or use the packaged app which bundles it.'
        )
    return backend


class UsbContext:
    def __init__(self, vid: hex, pid: hex, backend=None):
        dev = usb.core.find(idVendor=vid, idProduct=pid, backend=backend)
        if dev is None:
            raise ConnectionError(f'Device {vid}:{pid} not found')

        # On macOS, dev.reset() forces the Switch to re-enumerate, which
        # invalidates this handle and makes the following calls fail with
        # "[Errno 19] No such device". Skip it on Darwin.
        if sys.platform != 'darwin':
            dev.reset()

        # The device may already be configured; only set it if needed.
        try:
            if dev.get_active_configuration() is None:
                dev.set_configuration()
        except usb.core.USBError:
            dev.set_configuration()
        cfg = dev.get_active_configuration()

        self._out = usb.util.find_descriptor(
            cfg[(0, 0)],
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        self._in = usb.util.find_descriptor(
            cfg[(0, 0)],
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
        )

        if self._out is None:
            raise LookupError(f'Device {vid}:{pid} output endpoint not found')
        if self._in is None:
            raise LookupError(f'Device {vid}:{pid} input endpoint not found')

    def read(self, data_size, timeout=0):
        return self._in.read(data_size, timeout=timeout)

    def write(self, data, timeout=0):
        self._out.write(data, timeout=timeout)


def process_file_range_command(data_size, context, cache=None, on_event=None):
    log.info('File range')
    context.write(struct.pack('<4sIII', b'DBI0', CommandType.ACK, CommandID.FILE_RANGE, data_size))
    file_range_header = context.read(data_size)
    range_size = struct.unpack('<I', file_range_header[:4])[0]
    range_offset = struct.unpack('<Q', file_range_header[4:12])[0]
    nsp_name_len = struct.unpack('<I', file_range_header[12:16])[0]
    nsp_name = bytes(file_range_header[16:]).decode('utf-8')
    if cache is not None and len(cache) > 0:
        if nsp_name in cache:
            nsp_name = cache[nsp_name]

    display_name = os.path.basename(nsp_name)
    log.info(f'Range Size: {range_size}, Range Offset: {range_offset}, Name len: {nsp_name_len}, Name: {nsp_name}')

    response_bytes = struct.pack('<4sIII', b'DBI0', CommandType.RESPONSE, CommandID.FILE_RANGE, range_size)
    context.write(response_bytes)

    ack = bytes(context.read(16, timeout=0))
    cmd_type = struct.unpack('<I', ack[4:8])[0]
    cmd_id = struct.unpack('<I', ack[8:12])[0]
    data_size = struct.unpack('<I', ack[12:16])[0]
    log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')
    log.debug('Ack')

    with open(nsp_name, 'rb') as f:
        f.seek(range_offset)

        curr_off = 0x0
        end_off = range_size
        read_size = BUFFER_SEGMENT_DATA_SIZE

        _emit(on_event, 'transfer_start', name=display_name, total=range_size)
        while curr_off < end_off:
            if curr_off + read_size >= end_off:
                read_size = end_off - curr_off

            buf = f.read(read_size)
            context.write(data=buf, timeout=0)
            curr_off += read_size
            _emit(on_event, 'transfer_progress', name=display_name, done=curr_off, total=end_off)
        _emit(on_event, 'transfer_done', name=display_name, total=range_size)


def process_exit_command(context):
    log.info('Exit')
    context.write(struct.pack('<4sIII', b'DBI0', CommandType.RESPONSE, CommandID.EXIT, 0))


def process_list_command(context, work_dir_path, on_event=None):
    log.info('Get list')

    cached_titles = OrderedDict()
    for dirName, subdirList, fileList in os.walk(work_dir_path):
        log.debug(f'Found directory: {dirName}')
        for filename in fileList:
            if filename.lower().endswith('.nsp') or filename.lower().endswith('nsz') or filename.lower().endswith('.xci'):
                log.debug(f'\t{filename}')
                cached_titles[f'{filename}'] = str(Path(dirName).joinpath(filename))

    nsp_path_list = ''
    for title in cached_titles.keys():
        nsp_path_list += f'{title}\n'
    nsp_path_list_bytes = nsp_path_list.encode('utf-8')
    nsp_path_list_len = len(nsp_path_list_bytes)

    _emit(on_event, 'list', count=len(cached_titles), titles=list(cached_titles.keys()))

    context.write(struct.pack('<4sIII', b'DBI0', CommandType.RESPONSE, CommandID.LIST, nsp_path_list_len))

    ack = bytes(context.read(16, timeout=0))
    cmd_type = struct.unpack('<I', ack[4:8])[0]
    cmd_id = struct.unpack('<I', ack[8:12])[0]
    data_size = struct.unpack('<I', ack[12:16])[0]
    log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')
    log.debug('Ack')

    context.write(nsp_path_list_bytes)
    return cached_titles


def poll_commands(context, work_dir_path, should_stop=None, on_event=None):
    log.info('Entering command loop')

    cmd_cache = None
    while True:
        if should_stop is not None and should_stop():
            log.info('Stop requested')
            return

        try:
            cmd_header = bytes(context.read(16, timeout=1000))
        except usb.core.USBError as e:
            if _is_timeout(e):
                continue  # no command yet — loop so we can re-check should_stop
            raise

        if len(cmd_header) < 16:
            continue

        magic = cmd_header[:4]

        if magic != b'DBI0':  # Tinfoil USB Command 0
            continue

        cmd_type = struct.unpack('<I', cmd_header[4:8])[0]
        cmd_id = struct.unpack('<I', cmd_header[8:12])[0]
        data_size = struct.unpack('<I', cmd_header[12:16])[0]

        log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')

        if cmd_id == CommandID.EXIT:
            process_exit_command(context)
            _emit(on_event, 'status', text='DBI closed the connection')
            return
        elif cmd_id == CommandID.LIST:
            cmd_cache = process_list_command(context, work_dir_path, on_event=on_event)
        elif cmd_id == CommandID.FILE_RANGE:
            process_file_range_command(data_size, context=context, cache=cmd_cache, on_event=on_event)
        else:
            log.warning(f'Unknown command id: {cmd_id}')
            process_exit_command(context)
            return


def connect_to_switch(backend=None, should_stop=None, on_event=None):
    announced = False
    while True:
        if should_stop is not None and should_stop():
            return None
        try:
            return UsbContext(vid=SWITCH_VID, pid=SWITCH_PID, backend=backend)
        except (ConnectionError, usb.core.USBError):
            if not announced:
                log.info('Waiting for switch')
                _emit(on_event, 'status', text='Waiting for Switch — open DBI ▸ Install from USB')
                announced = True
            time.sleep(1)


def run_server(titles_path, backend=None, should_stop=None, on_event=None):
    """Run the install server against a Switch.

    Reconnects automatically after each session (e.g. when DBI is closed and
    reopened) until ``should_stop()`` returns True. Safe to call from a thread.
    """
    if not Path(titles_path).is_dir():
        raise NotADirectoryError('Specified path must be a directory')

    if backend is None:
        backend = get_libusb_backend()

    while should_stop is None or not should_stop():
        context = connect_to_switch(backend=backend, should_stop=should_stop, on_event=on_event)
        if context is None:  # stop requested while waiting
            break
        _emit(on_event, 'status', text='Connected — ready to install')
        try:
            poll_commands(context, titles_path, should_stop=should_stop, on_event=on_event)
        except usb.core.USBError as e:
            log.info(f'USB session ended: {e}')
            _emit(on_event, 'status', text='Switch disconnected — waiting to reconnect')
        # loop back around to wait for the next connection

    _emit(on_event, 'status', text='Stopped')


def get_args(args):
    parser = argparse.ArgumentParser(
        prog='dbibackend',
        description='Install local titles into Nintendo switch via USB',
        add_help=True
    )
    parent_group = parser.add_argument_group(title='Command line params')
    parent_group.add_argument('titles', type=str, help='Path to titles dir')
    parent_group.add_argument('--debug', action='store_true', default=False, required=False,
                              help='Enable debug output')
    return parser.parse_args(args)


def main():
    args = get_args(sys.argv[1:])

    if args.debug:
        log.setLevel(logging.DEBUG)

    if not Path(args.titles).is_dir():
        raise NotADirectoryError('Specified path must be a directory')

    run_server(args.titles)


if __name__ == '__main__':
    main()
