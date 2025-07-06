the dmg must be copied to the K-Configurator-Upate folder
or created using the ./create_dmg.sh 

the json file must define the verion number of that the above and the URL must be correct.
once working the URL should never need changing only the version.
I am using gh-pages to host the Json file and releases to host the dmg

to push change to gh-pages
git add update.jsaon   ( and whatever else you want to commit and push_
git commit -m "descr"
git push origin gh-pages.
this line is how you make the dmg with image from ../4dmg.png and the app from the build release folder
./create-uploadable-dmg.sh then....
gh release upload latest K-Configurator.dmg --clobber
This line uploads the binary asset to the release section of the repo 
from the K-Configurator-Update folder
latest is the tag
gh release upload latest K-Configurator.dmg --clobber


for git the origin in that folder is set to

MacBook-Pro--M4:K-Configurator-Update volovicg$ git remote -v
origin	https://github.com/volovicg/K-Configurator-Update.git (fetch)
origin	https://github.com/volovicg/K-Configurator-Update.git (push)

do all the above from the K-Configurator folder

