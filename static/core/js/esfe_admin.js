/* =====================================================
   ESFÉ – ADMIN BEHAVIOR SCRIPT
   ===================================================== */

document.addEventListener("DOMContentLoaded", function () {

    console.log("ESFé Admin System Loaded");

    // --------------------------------------------
    // Confirmation intelligente suppression
    // --------------------------------------------
    const deleteButtons = document.querySelectorAll(".deletelink");

    deleteButtons.forEach(btn => {
        btn.addEventListener("click", function (e) {
            const confirmDelete = confirm(
                "Confirmez-vous la suppression de cet élément ?"
            );
            if (!confirmDelete) {
                e.preventDefault();
            }
        });
    });

    // --------------------------------------------
    // Highlight menu actif
    // --------------------------------------------
    const currentUrl = window.location.pathname;
    const sidebarLinks = document.querySelectorAll(".nav-sidebar a");

    sidebarLinks.forEach(link => {
        if (currentUrl.includes(link.getAttribute("href"))) {
            link.classList.add("active");
        }
    });

});
