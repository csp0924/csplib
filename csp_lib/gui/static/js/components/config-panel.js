/**
 * Config Panel Component
 */
function configPanel() {
    return {
        yamlContent: '',
        importFile: null,
        importResult: null,

        async init() {
            await this.loadExport();
        },

        async loadExport() {
            try {
                const res = await fetch('/api/config/export');
                this.yamlContent = await res.text();
            } catch (e) {
                console.error('Failed to load config:', e);
            }
        },

        downloadYaml() {
            const blob = new Blob([this.yamlContent], { type: 'application/x-yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'csp_config.yaml';
            a.click();
            URL.revokeObjectURL(url);
        },

        handleFile(event) {
            this.importFile = event.target.files[0] || null;
            this.importResult = null;
        },

        async uploadConfig() {
            if (!this.importFile) return;
            const formData = new FormData();
            formData.append('file', this.importFile);
            try {
                const res = await fetch('/api/config/import', {
                    method: 'POST',
                    body: formData,
                });
                this.importResult = await res.json();
                await this.loadExport();
                // Refresh mode state
                const modeRes = await fetch('/api/modes');
                Alpine.store('app').modeState = await modeRes.json();
            } catch (e) {
                this.importResult = { status: 'error', errors: [String(e)] };
            }
        },
    };
}
