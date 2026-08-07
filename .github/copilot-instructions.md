Project description:

We have a VA page for Antimicrobial Stewardship guidance. It was build for the Minneapolis VA using VistA menu and order data to build out the repo, which then feeds a static github pages website where users access the guidance. This project is to take the Minneapolis guidance, make it scalable to new sites, and expose the contents to a CMS like Sveltia so that site SMEs can modify the guidance accordingly. This is the original Minneapolis site: https://antimicrobialcdss.github.io/MinneapolisCDSS.html

This is the site fed by our repo: [vhaantimicrobialstewardship.github.io](https://vhaantimicrobialstewardship.github.io/)

Current state:

* We've installed the Sveltia CMS in /admin.
* Changed the file/folder structure to put each station in its own folder for scalability
* Created a test station from Minneapolis's folder
* Created a Sveltia collection for just sinusitis and related pages to implement and test CMS features
* Edited the order menu json file to clear out extraneous information and combine the text so it can be edited in the rich text/markdown CMS editor
* Fixed a site caching issue - site must fetch the json files from network every time so that it shows recent updates from the CMS without having to clear the cache

Next steps:

* We have decided to unify the instructions instead of having separate guidance pages for inpat/outpat/ed. A team of SMEs is working on created the text for the unified pages, which we will then push to the site.
* Because the json files are too big to push to the CMS, and the user experience in the CMS is bad if there are too many items on the screen to edit, we need to subset the collections. We have decided to try to use the same logical groupings as from the homepage, with disease/syndrome categories etc.
