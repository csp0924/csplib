/**
 * CSP Control Panel - Global Alpine.js Store & App
 */

document.addEventListener('alpine:init', () => {
    // Global store
    Alpine.store('app', {
        devices: [],
        alarms: [],
        modeState: {},
        wsConnected: false,

        updateDeviceFromSnapshot(snapshot) {
            this.devices = snapshot.devices || [];
            this.modeState = {
                ...this.modeState,
                base_mode_names: snapshot.mode?.base_mode_names,
                active_override_names: snapshot.mode?.active_override_names,
                effective_mode: snapshot.mode?.effective_mode,
            };
        },

        updateDeviceValues(deviceId, pointName, newValue) {
            const device = this.devices.find(d => d.device_id === deviceId);
            if (device && device.latest_values) {
                device.latest_values[pointName] = newValue;
            }
        },

        updateDeviceConnection(deviceId, connected) {
            const device = this.devices.find(d => d.device_id === deviceId);
            if (device) {
                device.is_connected = connected;
                device.is_responsive = connected;
            }
        },
    });
});

function cspApp() {
    return {
        activeTab: 'dashboard',
        wsConnected: false,
        ws: null,
        devices: [],
        alarms: [],
        modeState: {},

        tabs: [
            { id: 'dashboard', label: 'Dashboard' },
            { id: 'points', label: 'Points' },
            { id: 'alarms', label: 'Alarms' },
            { id: 'commands', label: 'Commands' },
            { id: 'modes', label: 'Modes' },
            { id: 'config', label: 'Config' },
            { id: 'health', label: 'Health' },
        ],

        init() {
            this.fetchInitialState();
            this.connectWebSocket();
        },

        async fetchInitialState() {
            try {
                const [devRes, alarmRes, modeRes] = await Promise.all([
                    fetch('/api/devices'),
                    fetch('/api/alarms'),
                    fetch('/api/modes'),
                ]);
                this.devices = await devRes.json();
                this.alarms = await alarmRes.json();
                this.modeState = await modeRes.json();

                Alpine.store('app').devices = this.devices;
                Alpine.store('app').alarms = this.alarms;
                Alpine.store('app').modeState = this.modeState;
            } catch (e) {
                console.error('Failed to fetch initial state:', e);
            }
        },

        connectWebSocket() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = `${proto}//${location.host}/ws`;
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this.wsConnected = true;
                Alpine.store('app').wsConnected = true;
            };

            this.ws.onclose = () => {
                this.wsConnected = false;
                Alpine.store('app').wsConnected = false;
                // Auto-reconnect after 3s
                setTimeout(() => this.connectWebSocket(), 3000);
            };

            this.ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    this.handleMessage(msg);
                } catch (e) {
                    console.error('Failed to parse WS message:', e);
                }
            };
        },

        handleMessage(msg) {
            const store = Alpine.store('app');
            switch (msg.type) {
                case 'snapshot':
                    store.updateDeviceFromSnapshot(msg.data);
                    this.devices = store.devices;
                    this.modeState = {
                        ...this.modeState,
                        ...store.modeState,
                    };
                    break;
                case 'value_change':
                    store.updateDeviceValues(msg.device_id, msg.data.point_name, msg.data.new_value);
                    break;
                case 'connected':
                    store.updateDeviceConnection(msg.device_id, true);
                    break;
                case 'disconnected':
                    store.updateDeviceConnection(msg.device_id, false);
                    break;
                case 'alarm_triggered':
                    store.alarms.push({
                        device_id: msg.device_id,
                        ...msg.data,
                        is_active: true,
                        activated_at: msg.timestamp,
                    });
                    this.alarms = store.alarms;
                    break;
                case 'alarm_cleared':
                    store.alarms = store.alarms.filter(
                        a => !(a.device_id === msg.device_id && a.code === msg.data.code)
                    );
                    this.alarms = store.alarms;
                    break;
            }
        },
    };
}
