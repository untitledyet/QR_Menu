/**
 * FloorMap — Canvas-based restaurant table renderer.
 * Shared between customer view (read-only) and admin layout builder (editable).
 */
class FloorMap {
    constructor(canvasEl, options = {}) {
        this.canvas = canvasEl;
        this.ctx = canvasEl.getContext('2d');
        this.tables = [];
        this.editable = options.editable || false;
        this.onTableSelect = options.onTableSelect || null;
        this.onLayoutChange = options.onLayoutChange || null;
        this.selectedTableId = null;
        this.availability = {};
        this.dragging = null;
        this.dragOffset = { x: 0, y: 0 };

        this._bindEvents();
        this._resize();
        window.addEventListener('resize', () => this._resize());
    }

    _resize() {
        const parent = this.canvas.parentElement;
        this.canvas.width = parent.clientWidth;
        this.canvas.height = Math.max(400, parent.clientHeight);
        this.render();
    }

    _bindEvents() {
        this.canvas.addEventListener('click', (e) => this._onClick(e));
        if (this.editable) {
            this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
            this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
            this.canvas.addEventListener('mouseup', () => this._onMouseUp());
            this.canvas.addEventListener('touchstart', (e) => this._onTouchStart(e));
            this.canvas.addEventListener('touchmove', (e) => this._onTouchMove(e));
            this.canvas.addEventListener('touchend', () => this._onMouseUp());
        }
    }

    loadLayout(tables) {
        this.tables = (tables || []).map(t => ({ ...t }));
        this.render();
    }

    getLayout() {
        return this.tables.map(t => ({
            id: t.id, label: t.label, shape: t.shape, capacity: t.capacity,
            pos_x: t.pos_x, pos_y: t.pos_y, width: t.width, height: t.height,
        }));
    }

    setAvailability(map) {
        this.availability = map || {};
        this.render();
    }

    selectTable(tableId) {
        this.selectedTableId = tableId;
        this.render();
    }

    addTable(shape, capacity) {
        const id = 'new_' + Date.now();
        let w = 60, h = 60;
        if (shape === 'rectangle') { w = 110; h = 60; }
        this.tables.push({
            id, label: 'T' + (this.tables.length + 1), shape: shape || 'circle',
            capacity: capacity || 4, pos_x: 50 + Math.random() * 200,
            pos_y: 50 + Math.random() * 200, width: w, height: h,
        });
        this.render();
        if (this.onLayoutChange) this.onLayoutChange(this.getLayout());
    }

    removeTable(tableId) {
        this.tables = this.tables.filter(t => t.id !== tableId);
        if (this.selectedTableId === tableId) this.selectedTableId = null;
        this.render();
        if (this.onLayoutChange) this.onLayoutChange(this.getLayout());
    }

    render() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Background — use CSS variable or fallback
        const styles = getComputedStyle(document.documentElement);
        const bgColor = styles.getPropertyValue('--surface').trim() || styles.getPropertyValue('--bo-bg').trim() || '#1E1E2A';
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, w, h);

        // Grid dots
        ctx.fillStyle = 'rgba(128,128,128,0.1)';
        for (let x = 0; x < w; x += 20) {
            for (let y = 0; y < h; y += 20) {
                ctx.fillRect(x, y, 1, 1);
            }
        }

        // Get text color from CSS
        const textColor = styles.getPropertyValue('--text').trim() || '#E8E8F0';
        const mutedColor = styles.getPropertyValue('--text-muted').trim() || '#9CA3B8';

        // Tables — draw with chairs
        this.tables.forEach(t => {
            const isSelected = t.id === this.selectedTableId;
            const status = this.availability[t.id];
            let fillColor = styles.getPropertyValue('--card').trim() || '#2A2A3A';
            let strokeColor = styles.getPropertyValue('--border').trim() || '#3A3A4E';
            let chairColor = 'rgba(128,128,128,0.3)';

            if (status === 'available') { fillColor = 'rgba(16,185,129,0.2)'; strokeColor = '#10B981'; chairColor = 'rgba(16,185,129,0.4)'; }
            else if (status === 'reserved') { fillColor = 'rgba(239,68,68,0.2)'; strokeColor = '#EF4444'; chairColor = 'rgba(239,68,68,0.3)'; }
            if (isSelected) { fillColor = 'rgba(255,107,53,0.3)'; strokeColor = '#FF6B35'; chairColor = 'rgba(255,107,53,0.4)'; }

            const cx = t.pos_x + t.width / 2;
            const cy = t.pos_y + t.height / 2;
            const tw = t.width * 0.6;  // table is smaller, chairs around it
            const th = t.height * 0.6;

            ctx.save();

            // Draw chairs — simple symmetric placement
            const chairs = t.capacity || 4;
            ctx.fillStyle = chairColor;
            const chairR = 6;
            const gap = 8; // gap between chair and table edge

            if (t.shape === 'circle') {
                for (let i = 0; i < chairs; i++) {
                    const angle = (i / chairs) * Math.PI * 2 - Math.PI / 2;
                    const cr = tw / 2 + gap + chairR;
                    const chairX = cx + Math.cos(angle) * cr;
                    const chairY = cy + Math.sin(angle) * cr;
                    ctx.beginPath();
                    ctx.arc(chairX, chairY, chairR, 0, Math.PI * 2);
                    ctx.fill();
                }
            } else {
                // Square/rectangle: specific chair layout based on capacity
                const halfTW = tw / 2;
                const halfTH = (t.shape === 'square' ? tw : th) / 2;
                const chairPositions = [];

                if (chairs <= 2) {
                    // 2: left + right
                    chairPositions.push({ x: cx - halfTW - gap - chairR, y: cy });
                    chairPositions.push({ x: cx + halfTW + gap + chairR, y: cy });
                } else if (chairs <= 4) {
                    // 4: top, bottom, left, right
                    chairPositions.push({ x: cx, y: cy - halfTH - gap - chairR });
                    chairPositions.push({ x: cx, y: cy + halfTH + gap + chairR });
                    chairPositions.push({ x: cx - halfTW - gap - chairR, y: cy });
                    chairPositions.push({ x: cx + halfTW + gap + chairR, y: cy });
                } else if (chairs <= 6) {
                    // 6: long sides 2-2, short sides 1-1
                    const longSpacing = tw / 3;
                    chairPositions.push({ x: cx - longSpacing / 2, y: cy - halfTH - gap - chairR });
                    chairPositions.push({ x: cx + longSpacing / 2, y: cy - halfTH - gap - chairR });
                    chairPositions.push({ x: cx - longSpacing / 2, y: cy + halfTH + gap + chairR });
                    chairPositions.push({ x: cx + longSpacing / 2, y: cy + halfTH + gap + chairR });
                    chairPositions.push({ x: cx - halfTW - gap - chairR, y: cy });
                    chairPositions.push({ x: cx + halfTW + gap + chairR, y: cy });
                } else {
                    // 8: long sides 3-3, short sides 1-1
                    const longSpacing = tw / 4;
                    for (let i = 0; i < 3; i++) {
                        chairPositions.push({ x: cx - tw / 2 + longSpacing * (i + 0.5) + longSpacing / 2, y: cy - halfTH - gap - chairR });
                        chairPositions.push({ x: cx - tw / 2 + longSpacing * (i + 0.5) + longSpacing / 2, y: cy + halfTH + gap + chairR });
                    }
                    chairPositions.push({ x: cx - halfTW - gap - chairR, y: cy });
                    chairPositions.push({ x: cx + halfTW + gap + chairR, y: cy });
                }

                chairPositions.forEach(p => {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, chairR, 0, Math.PI * 2);
                    ctx.fill();
                });
            }

            // Draw table surface
            ctx.fillStyle = fillColor;
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = isSelected ? 3 : 1.5;

            if (t.shape === 'circle') {
                ctx.beginPath();
                ctx.arc(cx, cy, tw / 2, 0, Math.PI * 2);
                ctx.fill(); ctx.stroke();
            } else {
                const r = 6;
                const tx = t.pos_x + (t.width - tw) / 2;
                const ty = t.pos_y + (t.height - th) / 2;
                this._roundRect(ctx, tx, ty, tw, t.shape === 'square' ? tw : th, r);
                ctx.fill(); ctx.stroke();
            }

            // Label
            ctx.fillStyle = textColor;
            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(t.label, cx, cy - 5);

            ctx.font = '9px Inter, sans-serif';
            ctx.fillStyle = mutedColor;
            ctx.fillText(t.capacity + ' 👤', cx, cy + 8);

            ctx.restore();
        });
    }

    _roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    _getTableAt(x, y) {
        for (let i = this.tables.length - 1; i >= 0; i--) {
            const t = this.tables[i];
            const tw = t.shape === 'square' ? t.width : t.width;
            const th = t.shape === 'square' ? t.width : t.height;
            if (x >= t.pos_x && x <= t.pos_x + tw && y >= t.pos_y && y <= t.pos_y + th) return t;
        }
        return null;
    }

    _getCanvasPos(e) {
        const rect = this.canvas.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    _onClick(e) {
        const pos = this._getCanvasPos(e);
        const table = this._getTableAt(pos.x, pos.y);
        if (table) {
            if (this.onTableSelect) this.onTableSelect(table);
            this.selectedTableId = table.id;
            this.render();
        }
    }

    _onMouseDown(e) {
        const pos = this._getCanvasPos(e);
        const table = this._getTableAt(pos.x, pos.y);
        if (table) {
            this.dragging = table;
            this.dragOffset = { x: pos.x - table.pos_x, y: pos.y - table.pos_y };
        }
    }

    _onMouseMove(e) {
        if (!this.dragging) return;
        const pos = this._getCanvasPos(e);
        this.dragging.pos_x = pos.x - this.dragOffset.x;
        this.dragging.pos_y = pos.y - this.dragOffset.y;
        this.render();
    }

    _onMouseUp() {
        if (this.dragging && this.onLayoutChange) this.onLayoutChange(this.getLayout());
        this.dragging = null;
    }

    _onTouchStart(e) {
        e.preventDefault();
        const touch = e.touches[0];
        this._onMouseDown({ clientX: touch.clientX, clientY: touch.clientY });
    }

    _onTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        this._onMouseMove({ clientX: touch.clientX, clientY: touch.clientY });
    }
}
