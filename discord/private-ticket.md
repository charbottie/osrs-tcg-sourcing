Source: https://discord.com/channels/1522676267155980329/1528362221850333284

1. ### YAGPDB.xyzAPP _—_ 12:25 PM
    
    Welcome @Az Please describe the reasoning for opening this ticket, include any information you think may be relevant such as proof, other third parties and so on. use the following command to close the ticket `-ticket close reason for closing here` use the following command to add users to the ticket `-ticket adduser @user`
    

2. ### Az [TCG],  _—_ 12:26 PM
    
    opened it for you
    
3. @Lottie
    
4. I have a live collection sharing website ready for a future release that allows you to browse through the collection without using the plugin
    
5. It does indeed show everything that's available but only if using a debug flag in the URL.
    
6. Don't want to share that publicly on the server
    
7. ### Lottie [TCG], _—_ 12:28 PM
    
    Thanks so much! Was just about to do it but playing Top Trumps with my daughter ![😂](https://discord.com/assets/3eb3ebe2d01299ec.svg) That sounds awsome! Really excited to use it ![🙏](https://discord.com/assets/607676c4d5d72659.svg)
    
8. ### Az [TCG],  _—_ 12:28 PM
    
    [https://osrs-tcg.xyz/Azu?complete](https://osrs-tcg.xyz/Azu?complete "https://osrs-tcg.xyz/Azu?complete")
    
    [OSRS TCG](https://osrs-tcg.xyz/Azu?complete)
    
    OSRS-TCG — Live OSRS TCG collections.
    
9. This is my profile, the `?complete` at the end basically just adds every single card into the collection.
    
10. Currently requires a synced profile, mine should do for that purpose.
    
11. The live album sharing feature is not in the plugin hub version of the plugin and requires an API key.
    
12. those are the rendered versions of the cards. If you prefer to look at the cards in a json format: [https://osrs-tcg.xyz/catalog/Card.json](https://osrs-tcg.xyz/catalog/Card.json "https://osrs-tcg.xyz/catalog/Card.json")
    
13. ### Lottie [TCG], _—_ 12:32 PM
    
    json is perfect, this is really awesome man. Even has equipment slot. This is pro stuff!
    
14. ### Az [TCG],  _—_ 12:33 PM
    
    I wanted to keep things that might prove useful in the future.
    
15. ### Lottie [TCG], _—_ 12:34 PM
    
    Have you got in touch with the wiki guys? I wonder if they could help with some linking. I think the one thing holding this back from being a real gamemode long term is the manual searching. If you could get it to a level of click an npc you have unlocked and it shows what weapons / items you have from that... or vice versa you'll have a long-term success
    
16. ### Az [TCG],  _—_ 12:35 PM
    
    I have been in touch with the wiki guys, not for those reasons though
    
17. I assume you're referring to the Bronzeman TCG gamemode
    
18. ### Lottie [TCG], _—_ 12:35 PM
    
    It's one of the reasons when we did leagues we got them to create their task lookups and links.
    
19. Yea mostly talking about the use of it as an actual gamemode
    
20. ### Az [TCG],  _—_ 12:36 PM
    
    That would not be my field of expertise. I'm not involved in the Bronzeman TCG development directly.
    
21. I'm the developer of the core plugin with the card collection and all that.
    
22. ### Lottie [TCG], _—_ 12:37 PM
    
    Ahh reasonable, maybe one for felmeme. I mean the core is the basis of all of this. You should be proud
    
23. ### Az [TCG],  _—_ 12:38 PM
    
    The Bronzeman TCG plugin expands on the collection by actually restricting in-game actions and such.
    
24. I can add Felmeme to the ticket if you want to discuss the possibilities on the gamemode side of things with them.
    
25. ### Lottie [TCG], _—_ 12:39 PM
    
    Yea happy to if you're okay with that?
    
26. ### Az [TCG],  _—_ 12:39 PM
    
    I'm too dumb for all that, it's too logical
    
27. ### Lottie [TCG], _—_ 12:39 PM
    
    Hahaha, I doubt that, you've already created something awesome and logical
    
28. ### Az [TCG],  _—_ 12:39 PM
    
    Thanks for the compliments
    
29. Just a crazy idea we discussed with friends taken too far
    
30. ![:kekw:](https://cdn.discordapp.com/emojis/861314523653996574.webp?size=240)
    
31. @Felmeme
    
32. ### Lottie [TCG], _—_ 12:40 PM
    
    I mean it puts my favourite two things together, ripping packs and old school ![😂](https://discord.com/assets/3eb3ebe2d01299ec.svg)
    
33. ### Az [TCG],  _—_ 12:40 PM
    
    I'm getting thanked for finally making people do their skilling grinds
    
34. ![:OMEGALUL:](https://cdn.discordapp.com/emojis/463290625303773184.webp?size=240)
    
35. ### Lottie [TCG], _—_ 12:41 PM
    
    ![🤣](https://discord.com/assets/e5bddb2a9171637d.svg)
    
36. ### Felmeme [TCG],  _—_ 12:41 PM
    
    I've also been in touch with the wiki guys (they told me off for scraping the wiki too much)
    
37. ### Lottie [TCG], _—_ 12:42 PM
    
    ![😂](https://discord.com/assets/3eb3ebe2d01299ec.svg) uhoh, not the best way to start
    
38. ### Felmeme [TCG],  _—_ 12:42 PM
    
    Nah they were chill, just basically said "do it this way instead"
    
39. ### Az [TCG],  _—_ 12:42 PM
    
    you 2 go at it, I have lasagna to finish
    
40. ### Lottie [TCG], _—_ 12:42 PM
    
    Enjoy!!
    
41. ### Felmeme [TCG],  _—_ 12:44 PM
    
    Yeah manual searching is a thing I don't really know where to start addressing. The side panel is basically where I got to with it so far
    
42. If you have an idea in mind for anything I'm very open to collaborating on this all. I'd need to look into how to actually connect it all up to the wiki
    
43. Bronzeman basically just works off the names on the cards to do most of it's checks, there is likely a better way to do it but it just throws all the names in a json file and goes off that atm
    
44. ### Az [TCG],  _—_ 12:46 PM
    
    my card list doesn't have IDs for NPCs
    
45. and items
    
46. or anything for that matter
    
47. ### Lottie [TCG], _—_ 12:48 PM
    
    Yea, totally happy to collab. I think we'd need some id system but given every name is unique you could potentially backfill those. Ideally we chat to the rs wiki guys and get their thoughts and then figure out how to do it either on the wiki itself or in the plugin using a better lookup system.
    
48. I need to head out now, but happy to keep up the conversation later? I don't have wiki connections any more but sounds like you guys do?
    
49. ### Az [TCG],  _—_ 12:49 PM
    
    potentially yes
    
50. I'm happy to add anything that's necessary for the gamemode to get everything working.
    
51. but I have to say, I'm pretty busy with the vision of the base TCG plugin for now
    
52. @Lottie also big fan of your previous work. The data was always very interesting to look at!
    
53. ### Lottie [TCG], _—_ 12:51 PM
    
    That's totally fine, thanks for the offer though. Ideally it's relatively lightweight on the card side as it's mostly lookups. Also Fel... don't envy you on all these foil card rules ![😂](https://discord.com/assets/3eb3ebe2d01299ec.svg)
    
54. Thanks Az, appreciate it! Wish there was more data to look at after I left haha
    
55. ### Az [TCG],  _—_ 12:51 PM
    
    I was always wondering...
    
56. I have ~230k cave horror kills on my old main
    
57. I wanted to know how I'd rank up :(
    
58. ### Lottie [TCG], _—_ 12:52 PM
    
    Damn, I would've searched that for you for sure. That's a lot of kills ![😂](https://discord.com/assets/3eb3ebe2d01299ec.svg) I could call in a favour for you if you like, I still know some of the analysts
    
59. ### Az [TCG],  _—_ 12:52 PM
    
    ![:PauseChamp:](https://cdn.discordapp.com/emojis/695171998187257859.webp?size=240)
    
60. maybe another time
    
61. anyways, very good talking to you!
    
62. ### Lottie [TCG], _—_ 12:53 PM
    
    Sure ![👍](https://discord.com/assets/a4faf6864a96a042.svg) just let me know. You too!
    
63. ### Az [TCG],  _—_ 12:53 PM
    
    I will leave the ticket open if you need to message about something privately
    
64. ### Felmeme [TCG],  _—_ 12:57 PM
    
    Yeah just hit me up and feel free to DM too. Foil rules I have ideas for, basically just one click add items to exempt list but it's just one of the things in the idea list basically Gonna be no way to cover all the niche foil choices
    
65. ### Az [TCG],  _—_ 12:57 PM
    
    the ticket will be here until it's closed
    
66. If you guys don't mind, I'd like to keep an eye out in-case I have anything meaningful to say
    
67. ### Felmeme [TCG],  _—_ 12:58 PM
    
    Yeah for sure, would rather it that way anyway ![:KEKW:](https://cdn.discordapp.com/emojis/1080842672899641394.webp?size=96)
    
68. ### Az [TCG],  _—_ 12:58 PM
    
    It's very likely some changes will be required for the base plugin anyways