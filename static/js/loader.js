// Simple loader state
let isGenerating = false;

// Update loader display
function updateLoader(percentage) {
    const loader = document.querySelector('.loader-container');
    const loaderText = document.querySelector('.loader-text');
    
    // Ensure valid percentage (0-100)
    percentage = Math.min(100, Math.max(0, parseFloat(percentage) || 0));
    
    // Round to 1 decimal place
    const displayPercentage = Math.round(percentage * 10) / 10;
    
    if (percentage > 0) {
        // Show loader
        loader.style.display = 'flex';
        loader.style.opacity = '1';
        loaderText.textContent = `${displayPercentage.toFixed(1)}%`;
        
        // Update circular progress if present
        const circle = document.querySelector('.progress-circle');
        if (circle) {
            const circumference = 2 * Math.PI * 45;
            circle.style.strokeDashoffset = circumference - (percentage / 100) * circumference;
        }
    } else {
        // Hide loader
        loader.style.display = 'none';
        loaderText.textContent = '0.0%';
    }
    
    console.log(`Loader updated: ${displayPercentage.toFixed(1)}%`);
}

// Check generation status
async function checkGenerationStatus(loader, result, itemIds) {
    if (isGenerating) {
        console.warn('Generation status check already running');
        return;
    }
    
    isGenerating = true;
    let pollCount = 0;
    const maxPolls = 240; // 2 minutes at 500ms intervals
    
    const pollStatus = async () => {
        try {
            const response = await fetch('/api/generation-status');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Status response:', data);
            
            // Calculate progress
            let progress = data.progress_percentage;
            if (data.total_items > 0) {
                const itemProgress = (data.current_item / data.total_items) * 100;
                const typeProgress = data.total_types > 0 ? (data.current_type / data.total_types) * (100 / data.total_items) : 0;
                progress = itemProgress + typeProgress;
            }
            
            // Update loader with progress
            updateLoader(progress);
            
            // Check if generation is complete
            if (!data.is_generating) {
                console.log('Generation complete');
                updateLoader(100);
                isGenerating = false;
                
                // Wait for a moment to show 100%
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // Use final_url_key from status response if available, otherwise fall back to stored key
                const finalUrlKey = data.final_url_key || window.generatedUrlKey;
                
                if (!finalUrlKey) {
                    console.error('No URL key found for redirection');
                    showNotification('Error: Could not find results URL', 'error');
                    updateLoader(0);
                    return;
                }
                
                console.log('Redirecting to results with key:', finalUrlKey);
                // Redirect to results
                window.location.href = `/results?token=${finalUrlKey}`;
                return;
            }
            
            // Check for timeout
            if (++pollCount >= maxPolls) {
                console.warn('Generation status check timed out');
                showNotification('Generation is taking longer than expected. Please check the results page.', 'warning');
                
                // Use final_url_key from status response if available, otherwise fall back to stored key
                const finalUrlKey = data.final_url_key || window.generatedUrlKey;
                
                // Try to redirect if we have a URL key
                if (finalUrlKey) {
                    console.log('Timeout redirect to results with key:', finalUrlKey);
                    window.location.href = `/results?token=${finalUrlKey}`;
                } else {
                    updateLoader(0);
                }
                return;
            }
            
            // Continue polling
            setTimeout(pollStatus, 500);
        } catch (error) {
            console.error('Error checking status:', error);
            
            // Retry on error unless we've hit the limit
            if (++pollCount < maxPolls) {
                setTimeout(pollStatus, 2000);
            } else {
                console.error('Max retries reached');
                isGenerating = false;
                updateLoader(0);
                showNotification('Error checking generation status. Please try again.', 'error');
            }
        }
    };
    
    // Start polling
    pollStatus();
}

// Initialize loader on page load
document.addEventListener('DOMContentLoaded', () => {
    updateLoader(0);
});