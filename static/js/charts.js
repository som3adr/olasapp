/**
 * Charts and Interactive JavaScript for Hostel Management System
 */

// Global chart instances
let financialChart = null;
let expenseChart = null;

// Chart.js default configuration
Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.color = '#6c757d';

// Color palette for charts
const chartColors = {
    primary: '#0d6efd',
    success: '#198754',
    danger: '#dc3545',
    warning: '#ffc107',
    info: '#0dcaf0',
    secondary: '#6c757d',
    gradients: [
        'rgba(13, 110, 253, 0.8)',
        'rgba(25, 135, 84, 0.8)',
        'rgba(220, 53, 69, 0.8)',
        'rgba(255, 193, 7, 0.8)',
        'rgba(13, 202, 240, 0.8)',
        'rgba(108, 117, 125, 0.8)',
        'rgba(111, 66, 193, 0.8)',
        'rgba(214, 51, 132, 0.8)'
    ]
};

/**
 * Utility Functions
 */

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

// Format date
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Show loading state
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '<div class="text-center p-4"><div class="spinner"></div><p class="mt-2">Loading...</p></div>';
    }
}

// Show error state
function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="text-center p-4 text-danger">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <p>${message}</p>
            </div>
        `;
    }
}

/**
 * Chart Creation Functions
 */

// Create financial overview chart
function createFinancialChart(data, canvasId) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    // Destroy existing chart if it exists
    if (financialChart) {
        financialChart.destroy();
    }

    financialChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.month),
            datasets: [{
                label: 'Income',
                data: data.map(d => d.income),
                borderColor: chartColors.success,
                backgroundColor: 'rgba(25, 135, 84, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: chartColors.success,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 6,
                pointHoverRadius: 8
            }, {
                label: 'Expenses',
                data: data.map(d => d.expenses),
                borderColor: chartColors.danger,
                backgroundColor: 'rgba(220, 53, 69, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: chartColors.danger,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 6,
                pointHoverRadius: 8
            }, {
                label: 'Net Income',
                data: data.map(d => d.net),
                borderColor: chartColors.primary,
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                borderWidth: 3,
                fill: false,
                tension: 0.4,
                pointBackgroundColor: chartColors.primary,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 6,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + formatCurrency(context.parsed.y);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#6c757d'
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        color: '#6c757d',
                        callback: function(value) {
                            return formatCurrency(value);
                        }
                    }
                }
            },
            elements: {
                point: {
                    hoverBackgroundColor: '#fff'
                }
            }
        }
    });

    return financialChart;
}

// Create expense breakdown chart
function createExpenseChart(data, canvasId) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    // Destroy existing chart if it exists
    if (expenseChart) {
        expenseChart.destroy();
    }

    expenseChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.category.replace('_', ' ').toUpperCase()),
            datasets: [{
                data: data.map(d => d.amount),
                backgroundColor: chartColors.gradients,
                borderWidth: 3,
                borderColor: '#fff',
                hoverBorderWidth: 4,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        padding: 15,
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return context.label + ': ' + formatCurrency(context.parsed) + ' (' + percentage + '%)';
                        }
                    }
                }
            },
            cutout: '60%',
            animation: {
                animateRotate: true,
                animateScale: true
            }
        }
    });

    return expenseChart;
}

// Create inventory status chart
function createInventoryChart(data, canvasId) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.name),
            datasets: [{
                label: 'Current Stock',
                data: data.map(d => d.current_stock),
                backgroundColor: data.map(d => 
                    d.current_stock <= 0 ? chartColors.danger :
                    d.current_stock <= d.minimum_stock ? chartColors.warning :
                    chartColors.success
                ),
                borderRadius: 6,
                borderSkipped: false
            }, {
                label: 'Minimum Stock',
                data: data.map(d => d.minimum_stock),
                backgroundColor: 'rgba(108, 117, 125, 0.3)',
                borderColor: chartColors.secondary,
                borderWidth: 2,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top'
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y + ' units';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });

    return chart;
}

/**
 * Interactive Features
 */

// Smooth scroll to element
function scrollToElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
}

// Toggle sidebar on mobile
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('show');
    }
}

// Confirm deletion with custom message
function confirmDelete(message = 'Are you sure you want to delete this item?') {
    return confirm(message);
}

// Auto-hide alerts after 5 seconds
function autoHideAlerts() {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (alert && alert.parentNode) {
                alert.style.transition = 'opacity 0.5s ease';
                alert.style.opacity = '0';
                setTimeout(() => {
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }, 500);
            }
        }, 5000);
    });
}

// Format number inputs on blur
function formatNumberInput(input) {
    const value = parseFloat(input.value);
    if (!isNaN(value)) {
        input.value = value.toFixed(2);
    }
}

// Validate form before submission
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Update stock value calculation
function updateStockValue(currentStockId, costPerUnitId, resultId) {
    const currentStock = parseFloat(document.getElementById(currentStockId)?.value) || 0;
    const costPerUnit = parseFloat(document.getElementById(costPerUnitId)?.value) || 0;
    const resultElement = document.getElementById(resultId);
    
    if (resultElement) {
        const totalValue = currentStock * costPerUnit;
        resultElement.textContent = formatCurrency(totalValue);
    }
}

/**
 * Data Table Enhancements
 */

// Sort table columns
function sortTable(tableId, columnIndex, dataType = 'text') {
    const table = document.getElementById(tableId);
    if (!table) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const sortedRows = rows.sort((a, b) => {
        const aVal = a.children[columnIndex].textContent.trim();
        const bVal = b.children[columnIndex].textContent.trim();
        
        if (dataType === 'number') {
            return parseFloat(aVal) - parseFloat(bVal);
        } else if (dataType === 'date') {
            return new Date(aVal) - new Date(bVal);
        } else {
            return aVal.localeCompare(bVal);
        }
    });
    
    // Clear tbody and append sorted rows
    tbody.innerHTML = '';
    sortedRows.forEach(row => tbody.appendChild(row));
}

// Filter table rows
function filterTable(tableId, searchInputId) {
    const table = document.getElementById(tableId);
    const searchInput = document.getElementById(searchInputId);
    
    if (!table || !searchInput) return;

    const searchTerm = searchInput.value.toLowerCase();
    const rows = table.querySelectorAll('tbody tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

/**
 * Dashboard Widgets
 */

// Update dashboard counters with animation
function animateCounter(elementId, endValue, duration = 2000) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const startValue = 0;
    const increment = endValue / (duration / 16); // 60 FPS
    let currentValue = startValue;

    const timer = setInterval(() => {
        currentValue += increment;
        if (currentValue >= endValue) {
            element.textContent = Math.round(endValue);
            clearInterval(timer);
        } else {
            element.textContent = Math.round(currentValue);
        }
    }, 16);
}

// Real-time clock for dashboard
function updateClock() {
    const clockElement = document.getElementById('dashboard-clock');
    if (!clockElement) return;

    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
        hour12: true,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const dateString = now.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
    
    clockElement.innerHTML = `
        <div class="text-center">
            <div class="h4 mb-0">${timeString}</div>
            <small class="text-muted">${dateString}</small>
        </div>
    `;
}

/**
 * Form Enhancements
 */

// Auto-calculate totals in forms
function setupAutoCalculation() {
    const quantityInputs = document.querySelectorAll('input[name*="quantity"]');
    const priceInputs = document.querySelectorAll('input[name*="price"], input[name*="cost"]');
    
    [...quantityInputs, ...priceInputs].forEach(input => {
        input.addEventListener('input', function() {
            const row = this.closest('tr') || this.closest('.row');
            if (row) {
                const quantity = parseFloat(row.querySelector('input[name*="quantity"]')?.value) || 0;
                const price = parseFloat(row.querySelector('input[name*="price"], input[name*="cost"]')?.value) || 0;
                const totalElement = row.querySelector('.total-amount');
                
                if (totalElement) {
                    totalElement.textContent = formatCurrency(quantity * price);
                }
            }
        });
    });
}

// Set up date inputs with reasonable defaults
function setupDateInputs() {
    const dateInputs = document.querySelectorAll('input[type="date"]');
    const today = new Date().toISOString().split('T')[0];
    
    dateInputs.forEach(input => {
        if (!input.value && input.hasAttribute('data-default-today')) {
            input.value = today;
        }
    });
}

/**
 * Initialization
 */

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Set up auto-hide alerts
    autoHideAlerts();
    
    // Set up form enhancements
    setupAutoCalculation();
    setupDateInputs();
    
    // Set up number input formatting
    const numberInputs = document.querySelectorAll('input[type="number"]');
    numberInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.step === '0.01') {
                formatNumberInput(this);
            }
        });
    });
    
    // Set up responsive sidebar toggle
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', toggleSidebar);
    }
    
    // Start dashboard clock if element exists
    if (document.getElementById('dashboard-clock')) {
        updateClock();
        setInterval(updateClock, 1000);
    }
    
    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});

// Handle window resize for responsive charts
window.addEventListener('resize', function() {
    if (financialChart) {
        financialChart.resize();
    }
    if (expenseChart) {
        expenseChart.resize();
    }
});

// Export functions for global use
window.hostelManagement = {
    formatCurrency,
    formatDate,
    showLoading,
    showError,
    createFinancialChart,
    createExpenseChart,
    createInventoryChart,
    scrollToElement,
    toggleSidebar,
    confirmDelete,
    validateForm,
    updateStockValue,
    sortTable,
    filterTable,
    animateCounter
};
